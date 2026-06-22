from src.parser.parser import (
    Program, VarDecl, Assignment, IncDec, Print, Input,
    Literal, BinOp, UnaryOp, Identifier, If, While, For,
    FuncDef, Return, FuncCall, Break, Continue
)

class SemanticError(Exception):
    pass

class FunctionSymbol:
    def __init__(self, name, params, ret_type, node):
        self.name     = name
        self.params   = params   # [(type, name), ...]
        self.ret_type = ret_type # str or None
        self.node     = node

class SemanticAnalyzer:
    def __init__(self):
        self.globals   = {}       # name -> type
        self.functions = {}       # name -> FunctionSymbol
        self.scopes    = []       # stack of dicts
        self._loop_depth = 0      # tracks if break/continue are valid

    # ── scope helpers ──────────────────────────────────────────────────────

    def enter_scope(self):
        self.scopes.append({})

    def leave_scope(self):
        self.scopes.pop()
    def print_symbol_table(self):
        W = 70

        def hline():
            print("-" * W)

        def row(col1, col2, col3, col4, w1=20, w2=12, w3=12):
            w4 = W - w1 - w2 - w3 - 2
            print(f"  {col1:<{w1}}{col2:<{w2}}{col3:<{w3}}{col4:<{w4}}")

        print()
        print("=" * W)
        print("  SYMBOL TABLE".center(W))
        print("=" * W)

    # -- GLOBALS --
        print()
        print("  GLOBAL VARIABLES")
        hline()
        row("NAME", "TYPE", "SCOPE", "NOTES")
        hline()
        if self.globals:
            for name, typ in self.globals.items():
                row(name, typ, "global", "variable")
        else:
            print("  (no global variables)")
        hline()

    # -- FUNCTIONS --
        print()
        print("  FUNCTIONS")
        hline()
        row("NAME", "RETURN", "PARAMS", "SIGNATURE")
        hline()
        if self.functions:
            for fname, fs in self.functions.items():
                params_str = ", ".join(f"{t} {n}" for t, n in fs.params) or "(none)"
                sig = f"{fname}({params_str}) -> {fs.ret_type or 'void'}"
                row(fname, fs.ret_type or "void", f"{len(fs.params)} param(s)", sig)
        else:
            print("  (no functions defined)")
        hline()

    # -- PER-FUNCTION LOCALS --
        for fname, fs in self.functions.items():
            if not fs.params:
                continue
            print()
            print(f"  LOCALS -- {fname}()")
            hline()
            row("NAME", "TYPE", "SCOPE", "NOTES")
            hline()
            for ptype, pname in fs.params:
                row(pname, ptype, fname + "()", "parameter")
            hline()

        print()
    def define_var(self, name, typ):
        if self.scopes:
            self.scopes[-1][name] = typ
        else:
            self.globals[name] = typ

    def lookup_var(self, name):
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return self.globals.get(name)

    # ── main entry ─────────────────────────────────────────────────────────

    def analyze(self, node):
        if isinstance(node, Program):
            # first pass: register all function signatures
            for s in node.statements:
                if isinstance(s, FuncDef):
                    if s.name in self.functions:
                        raise SemanticError(f"Function '{s.name}' already defined")
                    # infer return type from body if not annotated
                    ret_type = s.ret_type or self._infer_return_type(s.body)
                    self.functions[s.name] = FunctionSymbol(
                        s.name, s.params, ret_type, s
                    )
            # second pass: analyze everything
            for s in node.statements:
                self.analyze(s)

        elif isinstance(node, FuncDef):
            fs = self.functions[node.name]
            self.enter_scope()
            for ptype, pname in fs.params:
                self.define_var(pname, ptype)
            for stmt in node.body:
                self.analyze(stmt)
            self.leave_scope()

        elif isinstance(node, VarDecl):
            target = self.scopes[-1] if self.scopes else self.globals
            if node.name in target:
                raise SemanticError(
                    f"Variable '{node.name}' already declared in this scope"
                )
            expr_type = None
            if node.expr:
                expr_type = self.eval_expr(node.expr)
                if not self._types_compatible(node.type, expr_type):
                    raise SemanticError(
                        f"Type mismatch in '{node.name}': "
                        f"declared {node.type!r} but got {expr_type!r}"
                    )
            target[node.name] = node.type

        elif isinstance(node, Assignment):
            var_type = self.lookup_var(node.name)
            if var_type is None:
                raise SemanticError(f"Variable '{node.name}' not declared")
            rhs_type = self.eval_expr(node.expr)
            # compound assignments only valid for numeric types
            if node.op in ("+=", "-=", "*=", "/="):
                if var_type not in ("int", "float"):
                    raise SemanticError(
                        f"Compound assignment {node.op!r} not valid for type {var_type!r}"
                    )
                if rhs_type not in ("int", "float"):
                    raise SemanticError(
                        f"Right-hand side of {node.op!r} must be numeric, got {rhs_type!r}"
                    )
            elif not self._types_compatible(var_type, rhs_type):
                raise SemanticError(
                    f"Type mismatch assigning to '{node.name}': "
                    f"expected {var_type!r}, got {rhs_type!r}"
                )

        elif isinstance(node, IncDec):
            var_type = self.lookup_var(node.name)
            if var_type is None:
                raise SemanticError(f"Variable '{node.name}' not declared")
            if var_type not in ("int", "float"):
                raise SemanticError(
                    f"'{node.op}' operator requires numeric type, got {var_type!r}"
                )

        elif isinstance(node, Print):
            self.eval_expr(node.expr)   # any type is printable

        elif isinstance(node, Input):
            if self.lookup_var(node.name) is None:
                raise SemanticError(f"Variable '{node.name}' not declared for input")

        elif isinstance(node, If):
            for cond, block in node.branches:
                if cond is not None:
                    ct = self.eval_expr(cond)
                    if ct != "bool":
                        raise SemanticError(
                            f"Condition in if/elif must be bool, got {ct!r}"
                        )
                self.enter_scope()
                for s in block:
                    self.analyze(s)
                self.leave_scope()

        elif isinstance(node, While):
            ct = self.eval_expr(node.cond)
            if ct != "bool":
                raise SemanticError(f"While condition must be bool, got {ct!r}")
            self._loop_depth += 1
            self.enter_scope()
            for s in node.body:
                self.analyze(s)
            self.leave_scope()
            self._loop_depth -= 1

        elif isinstance(node, For):
            self._loop_depth += 1
            self.enter_scope()
            if node.init:
                self.analyze(node.init)
            if node.cond:
                ct = self.eval_expr(node.cond)
                if ct != "bool":
                    raise SemanticError(f"For condition must be bool, got {ct!r}")
            if node.post:
                self.analyze(node.post)
            for s in node.body:
                self.analyze(s)
            self.leave_scope()
            self._loop_depth -= 1

        elif isinstance(node, Break):
            if self._loop_depth == 0:
                raise SemanticError("'break' used outside of a loop")

        elif isinstance(node, Continue):
            if self._loop_depth == 0:
                raise SemanticError("'continue' used outside of a loop")

        elif isinstance(node, FuncCall):
            if node.name not in self.functions:
                raise SemanticError(f"Function '{node.name}' not defined")
            fs = self.functions[node.name]
            if len(node.args) != len(fs.params):
                raise SemanticError(
                    f"Function '{node.name}' expects {len(fs.params)} args, "
                    f"got {len(node.args)}"
                )
            for i, (arg, (ptype, pname)) in enumerate(zip(node.args, fs.params)):
                at = self.eval_expr(arg)
                if not self._types_compatible(ptype, at):
                    raise SemanticError(
                        f"Argument {i+1} of '{node.name}': "
                        f"expected {ptype!r}, got {at!r}"
                    )

        elif isinstance(node, Return):
            if node.expr:
                self.eval_expr(node.expr)

        else:
            raise SemanticError(f"Unhandled node in semantic analysis: {type(node).__name__}")

    # ── type helpers ───────────────────────────────────────────────────────

    def _types_compatible(self, expected, got):
        """float can accept int (widening), everything else must match exactly."""
        if expected == got:
            return True
        if expected == "float" and got == "int":
            return True
        return False

    def _infer_return_type(self, body):
        """Walk a function body and infer return type from the first Return node."""
        for stmt in body:
            if isinstance(stmt, Return):
                if stmt.expr is None:
                    return None
                try:
                    return self.eval_expr(stmt.expr)
                except SemanticError:
                    return None
        return None

    # ── expression type evaluator ──────────────────────────────────────────

    def eval_expr(self, expr):
        if isinstance(expr, Literal):
            return expr.dtype

        if isinstance(expr, Identifier):
            t = self.lookup_var(expr.name)
            if t is None:
                raise SemanticError(f"Variable '{expr.name}' not declared")
            return t

        if isinstance(expr, UnaryOp):
            operand_type = self.eval_expr(expr.operand)
            if expr.op == "-":
                if operand_type not in ("int", "float"):
                    raise SemanticError(
                        f"Unary '-' requires numeric operand, got {operand_type!r}"
                    )
                return operand_type
            if expr.op == "!":
                if operand_type != "bool":
                    raise SemanticError(
                        f"Unary '!' requires bool operand, got {operand_type!r}"
                    )
                return "bool"
            raise SemanticError(f"Unknown unary operator {expr.op!r}")

        if isinstance(expr, BinOp):
            lt = self.eval_expr(expr.left)
            rt = self.eval_expr(expr.right)
            op = expr.op

            if op in ("+", "-", "*", "/", "%"):
                if lt in ("int", "float") and rt in ("int", "float"):
                    return "float" if "float" in (lt, rt) else "int"
                if op == "+" and lt == "string" and rt == "string":
                    return "string"   # string concatenation
                raise SemanticError(
                    f"Operator {op!r} not supported for types {lt!r} and {rt!r}"
                )
            if op in ("<", ">", "<=", ">="):
                if lt in ("int", "float") and rt in ("int", "float"):
                    return "bool"
                raise SemanticError(
                    f"Operator {op!r} requires numeric operands, got {lt!r} and {rt!r}"
                )
            if op in ("==", "!="):
                if lt == rt or self._types_compatible(lt, rt) or self._types_compatible(rt, lt):
                    return "bool"
                raise SemanticError(
                    f"Cannot compare {lt!r} and {rt!r} with {op!r}"
                )
            if op in ("&&", "||"):
                if lt == "bool" and rt == "bool":
                    return "bool"
                raise SemanticError(
                    f"Operator {op!r} requires bool operands, got {lt!r} and {rt!r}"
                )
            raise SemanticError(f"Unknown operator {op!r}")

        if isinstance(expr, FuncCall):
            if expr.name not in self.functions:
                raise SemanticError(f"Function '{expr.name}' not defined")
            fs = self.functions[expr.name]
            if len(expr.args) != len(fs.params):
                raise SemanticError(
                    f"Function '{expr.name}' expects {len(fs.params)} args, "
                    f"got {len(expr.args)}"
                )
            for i, (arg, (ptype, _)) in enumerate(zip(expr.args, fs.params)):
                at = self.eval_expr(arg)
                if not self._types_compatible(ptype, at):
                    raise SemanticError(
                        f"Arg {i+1} of '{expr.name}': expected {ptype!r}, got {at!r}"
                    )
            # return the declared/inferred return type (not hardcoded "int")
            return fs.ret_type or "int"

        raise SemanticError(f"Cannot evaluate expression of type {type(expr).__name__}")
