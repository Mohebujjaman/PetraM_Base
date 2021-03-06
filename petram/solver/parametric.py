import os
import traceback
import gc

from petram.model import Model
from petram.solver.solver_model import Solver, SolveStep
from petram.namespace_mixin import NS_mixin
import petram.debug as debug
dprint1, dprint2, dprint3 = debug.init_dprints('Parametric')
format_memory_usage = debug.format_memory_usage

assembly_methods = {'Full assemble': 0,
                    'Reuse matrix' : 1}

class Parametric(SolveStep, NS_mixin):
    '''
    parametric sweep of some model paramter
    and run solver
    '''
    can_delete = True
    has_2nd_panel = False
    
    def __init__(self, *args, **kwargs):
        SolveStep.__init__(self, *args, **kwargs)
        NS_mixin.__init__(self, *args, **kwargs)
        
    def init_solver(self):
        pass

    def panel1_param(self):
        v = self.get_panel1_value()
        return [["Initial value setting",   self.init_setting,  0, {},],
                ["physics model(blank=auto)",   self.phys_model,  0, {},],
                ["assembly method",  'Full assemble',  4, {"readonly": True,
                      "choices": assembly_methods.keys()}],
                self.make_param_panel('scanner',  v[2]),
                [ "save separate mesh",  True,  3, {"text":""}],
                ["inner solver", ''  ,2, None],
                ["clear working directory", False, 3, {"text":""}],
                ]
    
    def get_panel1_value(self):
        txt = assembly_methods.keys()[0]
        for k, n in assembly_methods.items():
            if n == self.assembly_method: txt = k

        return (self.init_setting,
                self.phys_model,
                str(txt),      
                str(self.scanner),    
                self.save_separate_mesh,
                self.get_inner_solver_names(),
                self.clear_wdir)

    def import_panel1_value(self, v):
        self.init_setting = str(v[0])                        
        self.phys_model = str(v[1])
        self.assembly_method = assembly_methods[v[-5]]
        self.scanner = v[-4]
        self.save_separate_mesh = v[-3]
        self.clear_wdir = v[-1]
        
    def get_inner_solver_names(self):
        names = [s.name() for s in self.get_active_solvers()]
        return ', '.join(names)

    '''
    def get_inner_solvers(self):
        return [self[k] for k in self if self[k].enabled]
    '''
    def attribute_set(self, v):
        v = super(Parametric, self).attribute_set(v)
        v['assembly_method'] = 0
        v['scanner'] = 'Scan("a", [1,2,3])'
        v['save_separate_mesh'] = True
        v['clear_wdir'] = False                        
        return v
    
    def get_possible_child(self):
        from petram.solver.std_solver_model import StdSolver        
        from petram.solver.mumps_model import MUMPS
        from petram.solver.gmres_model import GMRES
        return [StdSolver,]
    
    def get_scanner(self):
        try:
            scanner = self.eval_param_expr(str(self.scanner), 
                                           'scanner')[0]
        except:
            traceback.print_exc()
            return
        return scanner

    def get_default_ns(self):
        from petram.solver.parametric_scanner import Scan
        return {'Scan': Scan}

    def go_case_dir(self, engine, ksol, mkdir):
        od = os.getcwd()                    
        path = os.path.join(od, 'case' + str(ksol))
        if mkdir:
            engine.mkdir(path) 
            os.chdir(path)
            engine.cleancwd() 
        else:
            os.chdir(path)
        engine.symlink('../model.pmfm', 'model.pmfm')                    
        return od


    def _run_full_assembly(self, engine, solvers, scanner, is_first=True):
        for kcase, case in enumerate(scanner):
            self.prepare_form_sol_variables(engine)
            
            is_first = True
            self.init(engine)
            od = self.go_case_dir(engine, kcase, True)
            for ksolver, s in enumerate(solvers):
                is_first = s.run(engine, is_first=is_first)
                engine.add_FESvariable_to_NS(self.get_phys()) 
                engine.store_x()
                if self.solve_error[0]:
                    dprint1("Parametric failed " + self.name() + ":"  +
                            self.solve_error[1])
            os.chdir(od)
                        
    def _run_rhs_assembly(self, engine, solvers, scanner, is_first=True):

        self.prepare_form_sol_variables(engine)
        self.init(engine)
        
        l_scan = len(scanner)

        
        all_phys = self.get_phys()        
        phys_target = self.get_target_phys()
        
        linearsolver = None
        for ksolver, s in enumerate(solvers):
            RHS_ALL=[]
            instance = s.allocate_solver_instance(engine)

            phys_target = self.get_phys()
            phys_range = self.get_phys_range()
            
            for kcase, case in enumerate(scanner):

                if kcase == 0:
                     instance.set_blk_mask()                    
                     instance.assemble(inplace=False)
                else:
                     engine.set_update_flag('ParametricRHS')
                     engine.run_apply_essential(phys_target,
                                                phys_range,
                                                update=True)
                     engine.run_fill_X_block(update=True)
                     engine.run_assemble_b(phys_target, update=True) 
                     engine.run_assemble_blocks(instance.compute_A,
                                                instance.compute_rhs, 
                                                inplace = False,
                                                update=True)

                     
                A, X, RHS, Ae, B, M, depvars = instance.blocks
                mask = instance.blk_mask
                depvars = [x for i, x in enumerate(depvars)
                           if mask[0][i]]                
                if kcase == 0:
                    ls_type = instance.ls_type
                    phys_real = not s.is_complex()                     
                    AA = engine.finalize_matrix(A, mask, not phys_real,
                                    format = ls_type)
                    
                RHS_ALL.append(RHS)

                 
                if kcase == l_scan-1:
                    BB = engine.finalize_rhs(RHS_ALL, A ,X[0], mask,
                                             not phys_real,
                                             format = ls_type)

                    if linearsolver is None:
                        linearsolver = instance.allocate_linearsolver(s.is_complex(),
                                                                      engine)
                    linearsolver.SetOperator(AA,
                                 dist = engine.is_matrix_distributed,
                                 name = depvars)
        
                    XX = None
                    solall = linearsolver.Mult(BB, x=XX, case_base=0)
                    if not phys_real and s.assemble_real:
                        oprt = linearsolver.oprt
                        solall = instance.linearsolver_model.real_to_complex(solall,
                                                                         oprt)

                    for ksol in range(l_scan):
                        if ksol == 0:
                            instance.save_solution(mesh_only = True,
                                                   save_parmesh = s.save_parmesh )
                        A.reformat_central_mat(solall, ksol, X[0], mask)
                        instance.sol = X[0]
                        od = self.go_case_dir(engine,
                                              ksol,
                                              ksolver == 0)
                        instance.save_solution(ksol = ksol,
                                               skip_mesh = False, 
                                               mesh_only = False,
                                               save_parmesh=s.save_parmesh)
                        os.chdir(od)
                   
    
    def run(self, engine, is_first=True):
        #
        # is_first is not used
        #
        dprint1("Parametric Scan, ", self.assembly_method)
        if self.clear_wdir:
            engine.remove_solfiles()

        scanner = self.get_scanner()
        if scanner is None: return
        
        solvers = self.get_active_solvers()
        
        phys_models = []
        for s in solvers:
            for p in s.get_phys():
                if not p in phys_models: phys_models.append(p)
        scanner.set_phys_models(phys_models)
        

        
        if self.assembly_method == 0: 
            self._run_full_assembly(engine, solvers, scanner, is_first=is_first)
        else:
            self._run_rhs_assembly(engine, solvers, scanner, is_first=is_first)
            
        
