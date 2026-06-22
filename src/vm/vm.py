from src.ir.ir_generator import Instr

MAX_CALL_DEPTH = 500


class VMError(Exception):
    pass


class Frame:
    def __init__(self, func_name, ret_addr):
        self.func_name = func_name
        self.vars      = {}
        self.ret_addr  = ret_addr


class VM:
    def __init__(self, instrs):
        self.instrs  = instrs
        self.labels  = {}
        self._build_label_index()
        self.globals    = {}
        self.temps      = {}
        self.call_stack = []   # list of Frame
        self.ret_temp   = None
        self.arg_stack  = []

    # ── setup ─────────────────────────────────────────────────────────────────

    def _build_label_index(self):
        for i, ins in enumerate(self.instrs):
            if ins.op == "LABEL":
                self.labels[ins.args[0]] = i

    # ── run ───────────────────────────────────────────────────────────────────

    def run(self):
        pc = 0
        while pc < len(self.instrs):
            ins = self.instrs[pc]
            op  = ins.op
            args = ins.args

            # ── memory ────────────────────────────────────────────────────────
            if op == "ALLOC":
                self._set_var(args[0], None)

            elif op == "STORE":
                name, src = args
                self._set_var(name, self._read(src))

            elif op == "LOAD_CONST":
                t, val = args
                self.temps[t] = val

            # ── arithmetic ────────────────────────────────────────────────────
            elif op in ("ADD", "SUB", "MUL", "DIV", "MOD"):
                t, l, r = args
                lv = self._read(l)
                rv = self._read(r)
                if op in ("DIV", "MOD"):
                    if rv == 0:
                        raise VMError(
                            f"Runtime error: division by zero at instruction {pc}"
                        )
                ops = {
                    "ADD": lambda a, b: a + b,
                    "SUB": lambda a, b: a - b,
                    "MUL": lambda a, b: a * b,
                    "DIV": lambda a, b: a / b,
                    "MOD": lambda a, b: a % b,
                }
                self.temps[t] = ops[op](lv, rv)

            # ── comparison ────────────────────────────────────────────────────
            elif op in ("EQ", "NE", "LT", "GT", "LE", "GE"):
                t, l, r = args
                lv, rv = self._read(l), self._read(r)
                ops = {
                    "EQ": lambda a, b: a == b, "NE": lambda a, b: a != b,
                    "LT": lambda a, b: a <  b, "GT": lambda a, b: a >  b,
                    "LE": lambda a, b: a <= b, "GE": lambda a, b: a >= b,
                }
                self.temps[t] = ops[op](lv, rv)

            # ── logical ───────────────────────────────────────────────────────
            elif op == "AND":
                t, l, r = args
                self.temps[t] = bool(self._read(l)) and bool(self._read(r))

            elif op == "OR":
                t, l, r = args
                self.temps[t] = bool(self._read(l)) or bool(self._read(r))

            elif op == "NOT":
                t, src = args
                self.temps[t] = not bool(self._read(src))

            # ── unary negation ────────────────────────────────────────────────
            elif op == "NEG":
                t, src = args
                v = self._read(src)
                if not isinstance(v, (int, float)):
                    raise VMError(f"NEG requires numeric value, got {type(v).__name__!r}")
                self.temps[t] = -v

            # ── I/O ───────────────────────────────────────────────────────────
            elif op == "PRINT":
                v = self._read(args[0])
                # format booleans as lowercase true/false
                if isinstance(v, bool):
                    print("true" if v else "false")
                else:
                    print(v)

            elif op == "INPUT":
                name = args[0]
                raw  = input()
                try:
                    val = float(raw) if "." in raw else int(raw)
                except ValueError:
                    val = raw
                self._set_var(name, val)

            # ── control flow ─────────────────────────────────────────────────
            elif op == "LABEL":
                pass  # already indexed

            elif op == "JUMP":
                label = args[0]
                self._check_label(label, pc)
                pc = self.labels[label]
                continue

            elif op == "JUMP_IF_FALSE":
                cond_t, label = args
                if not self._read(cond_t):
                    self._check_label(label, pc)
                    pc = self.labels[label]
                    continue

            # ── function call ─────────────────────────────────────────────────
            elif op == "PUSH_ARG":
                self.arg_stack.append(self._read(args[0]))

            elif op == "CALL":
                fname, nargs = args[0], int(args[1])
                label = f"func_{fname}"
                self._check_label(label, pc)

                if len(self.call_stack) >= MAX_CALL_DEPTH:
                    raise VMError(
                        f"Stack overflow: call depth exceeded {MAX_CALL_DEPTH} "
                        f"(possible infinite recursion in '{fname}')"
                    )

                frame = Frame(func_name=fname, ret_addr=pc + 1)
                vals  = self.arg_stack[-nargs:] if nargs > 0 else []
                self.arg_stack = self.arg_stack[:-nargs] if nargs > 0 else self.arg_stack

                # bind args by position
                for i, v in enumerate(vals):
                    frame.vars[f"arg{i}"] = v

                self.call_stack.append(frame)
                pc = self.labels[label]
                continue

            elif op == "POP_RET":
                t = args[0]
                self.temps[t] = self.ret_temp
                self.ret_temp = None

            elif op == "RETVAL":
                self.ret_temp = self._read(args[0])

            elif op == "RET":
                if not self.call_stack:
                    return  # top-level return
                frame = self.call_stack.pop()
                pc    = frame.ret_addr
                continue

            else:
                raise VMError(f"Unknown opcode {op!r} at instruction {pc}")

            pc += 1

    # ── helpers ───────────────────────────────────────────────────────────────

    def _set_var(self, name, value):
        if self.call_stack:
            self.call_stack[-1].vars[name] = value
        else:
            self.globals[name] = value

    def _read(self, x):
        """Resolve a temp name, variable name, or literal value."""
        if isinstance(x, (int, float, bool)):
            return x
        if isinstance(x, str):
            if x in self.temps:
                return self.temps[x]
            if self.call_stack:
                frame = self.call_stack[-1]
                if x in frame.vars:
                    return frame.vars[x]
            if x in self.globals:
                return self.globals[x]
            # last resort: try to parse as a numeric literal
            try:
                return float(x) if "." in x else int(x)
            except (ValueError, TypeError):
                return x
        return x

    def _check_label(self, label, pc):
        if label not in self.labels:
            raise VMError(f"Unknown label {label!r} referenced at instruction {pc}")
