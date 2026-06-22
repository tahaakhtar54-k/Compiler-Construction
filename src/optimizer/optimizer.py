from src.ir.ir_generator import Instr


class IROptimizer:
    """
    Multi-pass optimizer for the IR instruction stream.

    Pass 1 — Constant Folding   : replace arithmetic on known constants with
                                   a single LOAD_CONST.
    Pass 2 — Copy Propagation   : replace uses of a temp that is just a copy
                                   of another variable/temp with the original.
    Pass 3 — Dead Code Elim.    : remove STORE/LOAD_CONST whose result is
                                   never read before being overwritten.
    Pass 4 — Unreachable Code   : remove instructions that follow an
                                   unconditional JUMP / RET and precede the
                                   next LABEL (they can never execute).
    """

    def __init__(self, instrs):
        self.instrs = list(instrs)

    def optimize(self):
        code = self.instrs
        code = self._constant_folding(code)
        code = self._copy_propagation(code)
        code = self._dead_code_elimination(code)
        code = self._remove_unreachable(code)
        return code

    # ── Pass 1: Constant Folding ──────────────────────────────────────────────

    def _constant_folding(self, instrs):
        constants = {}   # temp/var name -> known constant value
        result    = []

        for ins in instrs:
            op, args = ins.op, ins.args

            if op == "LOAD_CONST":
                dest, val = args
                constants[dest] = val
                result.append(ins)

            elif op in ("ADD", "SUB", "MUL", "DIV", "MOD"):
                dest, l, r = args
                lv = constants.get(l)
                rv = constants.get(r)
                if (lv is not None and rv is not None
                        and isinstance(lv, (int, float))
                        and isinstance(rv, (int, float))):
                    try:
                        folded = {
                            "ADD": lv + rv,
                            "SUB": lv - rv,
                            "MUL": lv * rv,
                            "DIV": lv / rv   if rv != 0 else None,
                            "MOD": lv % rv   if rv != 0 else None,
                        }[op]
                        if folded is not None:
                            constants[dest] = folded
                            result.append(Instr("LOAD_CONST", (dest, folded)))
                            continue
                    except Exception:
                        pass
                constants.pop(dest, None)
                result.append(ins)

            elif op in ("EQ", "NE", "LT", "GT", "LE", "GE"):
                dest, l, r = args
                lv = constants.get(l)
                rv = constants.get(r)
                if lv is not None and rv is not None:
                    try:
                        folded = {
                            "EQ": lv == rv, "NE": lv != rv,
                            "LT": lv <  rv, "GT": lv >  rv,
                            "LE": lv <= rv, "GE": lv >= rv,
                        }[op]
                        constants[dest] = folded
                        result.append(Instr("LOAD_CONST", (dest, folded)))
                        continue
                    except Exception:
                        pass
                constants.pop(dest, None)
                result.append(ins)

            elif op == "NEG":
                dest, src = args
                sv = constants.get(src)
                if sv is not None and isinstance(sv, (int, float)):
                    constants[dest] = -sv
                    result.append(Instr("LOAD_CONST", (dest, -sv)))
                    continue
                constants.pop(dest, None)
                result.append(ins)

            elif op == "NOT":
                dest, src = args
                sv = constants.get(src)
                if sv is not None and isinstance(sv, bool):
                    constants[dest] = not sv
                    result.append(Instr("LOAD_CONST", (dest, not sv)))
                    continue
                constants.pop(dest, None)
                result.append(ins)

            elif op == "STORE":
                name, src = args
                val = constants.get(src)
                if val is not None:
                    constants[name] = val
                else:
                    constants.pop(name, None)
                result.append(ins)

            elif op in ("LABEL", "JUMP", "JUMP_IF_FALSE", "CALL"):
                # control-flow: flush constant table conservatively
                constants = {}
                result.append(ins)

            else:
                result.append(ins)

        return result

    # ── Pass 2: Copy Propagation ──────────────────────────────────────────────

    def _copy_propagation(self, instrs):
        """
        If we see  STORE x t1  and t1 is just another variable/temp,
        forward uses of x to t1 where safe.
        Also eliminates  STORE x x  (no-op stores).
        """
        copies = {}   # dest -> src (only when src is a simple name, not literal)
        result = []

        def resolve(name):
            seen = set()
            while name in copies and name not in seen:
                seen.add(name)
                name = copies[name]
            return name

        for ins in instrs:
            op, args = ins.op, ins.args

            if op == "STORE":
                name, src = args
                # Never forward argN names — they are internal VM binding slots,
                # not real variable values yet at copy-prop time.
                if isinstance(src, str) and src.startswith("arg"):
                    copies.pop(name, None)
                    result.append(ins)
                    continue
                resolved_src = resolve(src)
                if resolved_src == name:
                    # STORE x x — no-op, skip
                    continue
                # record copy relationship only for simple names
                copies[name] = resolved_src
                result.append(Instr(op, (name, resolved_src)))

            elif op == "LOAD_CONST":
                dest, val = args
                copies.pop(dest, None)   # dest is now a constant, not a copy
                result.append(ins)

            elif op in ("LABEL", "JUMP", "JUMP_IF_FALSE", "CALL"):
                copies = {}
                result.append(ins)

            else:
                # rewrite args using resolved copies
                new_args = tuple(resolve(a) if isinstance(a, str) else a for a in args)
                result.append(Instr(op, new_args))

        return result

    # ── Pass 3: Dead Code Elimination ─────────────────────────────────────────

    def _dead_code_elimination(self, instrs):
        """
        Remove LOAD_CONST / STORE to a temp that is never used after assignment,
        or is overwritten before any read.
        Only eliminates temporaries (names starting with 't') to stay safe.
        """
        # Count reads of each temp
        read_count = {}
        write_pos  = {}  # name -> list of instruction indices where it's written

        for i, ins in enumerate(instrs):
            op, args = ins.op, ins.args
            # reads: all args except the destination (first arg for ops that write)
            write_ops = {"LOAD_CONST", "STORE", "ADD", "SUB", "MUL", "DIV",
                         "MOD", "EQ", "NE", "LT", "GT", "LE", "GE",
                         "AND", "OR", "NEG", "NOT", "POP_RET"}
            if op in write_ops and args:
                dest = args[0]
                write_pos.setdefault(dest, []).append(i)
                read_args = args[1:]
            else:
                read_args = args

            for a in read_args:
                if isinstance(a, str):
                    read_count[a] = read_count.get(a, 0) + 1

        dead = set()
        for name, positions in write_pos.items():
            if name.startswith("t") and read_count.get(name, 0) == 0:
                dead.update(positions)

        return [ins for i, ins in enumerate(instrs) if i not in dead]

    # ── Pass 4: Remove Unreachable Code ───────────────────────────────────────

    def _remove_unreachable(self, instrs):
        """
        After an unconditional JUMP or RET, instructions up to the next
        LABEL are unreachable and can be dropped.
        """
        result      = []
        unreachable = False

        for ins in instrs:
            if ins.op == "LABEL":
                unreachable = False   # a label makes code reachable again
                result.append(ins)
            elif unreachable:
                continue              # drop unreachable instruction
            else:
                result.append(ins)
                if ins.op in ("JUMP", "RET"):
                    unreachable = True

        return result
