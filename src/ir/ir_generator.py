from dataclasses import dataclass
from src.parser.parser import (
    Program, VarDecl, Assignment, IncDec, Print, Input,
    Literal, BinOp, UnaryOp, Identifier, If, While, For,
    FuncDef, Return, FuncCall, Break, Continue
)

@dataclass
class Instr:
    op: str
    args: tuple

    def __repr__(self):
        return f"{self.op} {' '.join(str(a) for a in self.args)}"


class IRGenerator:
    def __init__(self):
        self.code        = []
        self.temp_count  = 0
        self.label_count = 0
        # stacks for break/continue label resolution inside loops
        self._break_stack    = []   # stack of end-labels
        self._continue_stack = []   # stack of continue-point labels

    # ── helpers ──────────────────────────────────────────────────────────────

    def new_temp(self):
        self.temp_count += 1
        return f"t{self.temp_count}"

    def new_label(self, base="L"):
        self.label_count += 1
        return f"{base}{self.label_count}"

    def emit(self, op, *args):
        self.code.append(Instr(op, args))

    # ── main generator ───────────────────────────────────────────────────────

    def gen(self, node):
        # ── program ──────────────────────────────────────────────────────────
        if isinstance(node, Program):
            has_funcs = any(isinstance(s, FuncDef) for s in node.statements)
            main_label = None
            if has_funcs:
                main_label = self.new_label("MAIN")
                self.emit("JUMP", main_label)  # skip over function bodies at startup
            for s in node.statements:
                if isinstance(s, FuncDef):
                    self.gen(s)
            if main_label:
                self.emit("LABEL", main_label)
            for s in node.statements:
                if not isinstance(s, FuncDef):
                    self.gen(s)

        # ── variable declaration ──────────────────────────────────────────────
        elif isinstance(node, VarDecl):
            if node.expr:
                src = self.gen(node.expr)
                self.emit("STORE", node.name, src)
            else:
                self.emit("ALLOC", node.name)

        # ── assignment (plain = and compound +=  -=  *=  /=) ────────────────
        elif isinstance(node, Assignment):
            if node.op == "=":
                src = self.gen(node.expr)
                self.emit("STORE", node.name, src)
            else:
                # desugar: x += e  →  x = x + e
                op_map = {"+=": "ADD", "-=": "SUB", "*=": "MUL", "/=": "DIV"}
                rhs  = self.gen(node.expr)
                t    = self.new_temp()
                self.emit(op_map[node.op], t, node.name, rhs)
                self.emit("STORE", node.name, t)

        # ── i++ / i-- ────────────────────────────────────────────────────────
        elif isinstance(node, IncDec):
            one = self.new_temp()
            t   = self.new_temp()
            self.emit("LOAD_CONST", one, 1)
            op_ir = "ADD" if node.op == "++" else "SUB"
            self.emit(op_ir, t, node.name, one)
            self.emit("STORE", node.name, t)

        # ── print ─────────────────────────────────────────────────────────────
        elif isinstance(node, Print):
            src = self.gen(node.expr)
            self.emit("PRINT", src)

        # ── input ─────────────────────────────────────────────────────────────
        elif isinstance(node, Input):
            self.emit("INPUT", node.name)

        # ── literals ──────────────────────────────────────────────────────────
        elif isinstance(node, Literal):
            t = self.new_temp()
            self.emit("LOAD_CONST", t, node.value)
            return t

        # ── identifier ────────────────────────────────────────────────────────
        elif isinstance(node, Identifier):
            return node.name

        # ── unary operators ───────────────────────────────────────────────────
        elif isinstance(node, UnaryOp):
            operand = self.gen(node.operand)
            t = self.new_temp()
            if node.op == "-":
                self.emit("NEG", t, operand)
            elif node.op == "!":
                self.emit("NOT", t, operand)
            return t

        # ── binary operators with short-circuit for && and || ─────────────────
        elif isinstance(node, BinOp):
            if node.op == "&&":
                return self._gen_short_circuit_and(node)
            if node.op == "||":
                return self._gen_short_circuit_or(node)

            l = self.gen(node.left)
            r = self.gen(node.right)
            t = self.new_temp()
            op_map = {
                "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
                "==": "EQ", "!=": "NE", "<": "LT", ">": "GT",
                "<=": "LE", ">=": "GE",
            }
            self.emit(op_map.get(node.op, node.op), t, l, r)
            return t

        # ── if / elif / else ──────────────────────────────────────────────────
        elif isinstance(node, If):
            end_label = self.new_label("ENDIF")
            for i, (cond, block) in enumerate(node.branches):
                if cond is None:
                    # else block — no condition check
                    for s in block:
                        self.gen(s)
                else:
                    next_label = self.new_label("ELIF" if i + 1 < len(node.branches) else "ELSE")
                    cond_t = self.gen(cond)
                    self.emit("JUMP_IF_FALSE", cond_t, next_label)
                    for s in block:
                        self.gen(s)
                    self.emit("JUMP", end_label)
                    self.emit("LABEL", next_label)
            self.emit("LABEL", end_label)

        # ── while ─────────────────────────────────────────────────────────────
        elif isinstance(node, While):
            start = self.new_label("WHILE_START")
            end   = self.new_label("WHILE_END")
            self._break_stack.append(end)
            self._continue_stack.append(start)
            self.emit("LABEL", start)
            cond = self.gen(node.cond)
            self.emit("JUMP_IF_FALSE", cond, end)
            for s in node.body:
                self.gen(s)
            self.emit("JUMP", start)
            self.emit("LABEL", end)
            self._break_stack.pop()
            self._continue_stack.pop()

        # ── for ───────────────────────────────────────────────────────────────
        elif isinstance(node, For):
            start    = self.new_label("FOR_START")
            post_lbl = self.new_label("FOR_POST")
            end      = self.new_label("FOR_END")
            self._break_stack.append(end)
            self._continue_stack.append(post_lbl)
            if node.init:
                self.gen(node.init)
            self.emit("LABEL", start)
            if node.cond:
                ct = self.gen(node.cond)
                self.emit("JUMP_IF_FALSE", ct, end)
            for s in node.body:
                self.gen(s)
            self.emit("LABEL", post_lbl)
            if node.post:
                self.gen(node.post)
            self.emit("JUMP", start)
            self.emit("LABEL", end)
            self._break_stack.pop()
            self._continue_stack.pop()

        # ── break / continue ──────────────────────────────────────────────────
        elif isinstance(node, Break):
            self.emit("JUMP", self._break_stack[-1])

        elif isinstance(node, Continue):
            self.emit("JUMP", self._continue_stack[-1])

        # ── function definition ───────────────────────────────────────────────
        elif isinstance(node, FuncDef):
            self.emit("LABEL", f"func_{node.name}")
            for i, (ptype, pname) in enumerate(node.params):
                self.emit("STORE", pname, f"arg{i}")
            for s in node.body:
                self.gen(s)
            self.emit("RET")

        # ── return ────────────────────────────────────────────────────────────
        elif isinstance(node, Return):
            if node.expr:
                v = self.gen(node.expr)
                self.emit("RETVAL", v)
            self.emit("RET")

        # ── function call ─────────────────────────────────────────────────────
        elif isinstance(node, FuncCall):
            arg_temps = [self.gen(a) for a in node.args]
            for at in arg_temps:
                self.emit("PUSH_ARG", at)
            self.emit("CALL", node.name, len(arg_temps))
            t = self.new_temp()
            self.emit("POP_RET", t)
            return t

        else:
            raise Exception(f"IR: unsupported node type {type(node).__name__}")

    # ── short-circuit helpers ─────────────────────────────────────────────────

    def _gen_short_circuit_and(self, node):
        """x && y  →  if !x jump to false_lbl, else eval y"""
        false_lbl = self.new_label("AND_FALSE")
        end_lbl   = self.new_label("AND_END")
        result    = self.new_temp()

        lv = self.gen(node.left)
        self.emit("JUMP_IF_FALSE", lv, false_lbl)
        rv = self.gen(node.right)
        self.emit("JUMP_IF_FALSE", rv, false_lbl)
        self.emit("LOAD_CONST", result, True)
        self.emit("JUMP", end_lbl)
        self.emit("LABEL", false_lbl)
        self.emit("LOAD_CONST", result, False)
        self.emit("LABEL", end_lbl)
        return result

    def _gen_short_circuit_or(self, node):
        """x || y  →  if x jump to true_lbl, else eval y"""
        true_lbl = self.new_label("OR_TRUE")
        end_lbl  = self.new_label("OR_END")
        result   = self.new_temp()

        lv = self.gen(node.left)
        # if lv is truthy jump to true
        not_lv = self.new_temp()
        self.emit("NOT", not_lv, lv)
        self.emit("JUMP_IF_FALSE", not_lv, true_lbl)
        rv = self.gen(node.right)
        not_rv = self.new_temp()
        self.emit("NOT", not_rv, rv)
        self.emit("JUMP_IF_FALSE", not_rv, true_lbl)
        self.emit("LOAD_CONST", result, False)
        self.emit("JUMP", end_lbl)
        self.emit("LABEL", true_lbl)
        self.emit("LOAD_CONST", result, True)
        self.emit("LABEL", end_lbl)
        return result
