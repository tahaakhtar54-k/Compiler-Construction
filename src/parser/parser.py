from dataclasses import dataclass, field
from typing import List, Optional
from src.lexer.lexer import Token

class ParseError(Exception):
    pass

# ── AST nodes ────────────────────────────────────────────────────────────────

@dataclass
class Node: pass

@dataclass
class Program(Node):
    statements: List[Node]

@dataclass
class VarDecl(Node):
    type: str
    name: str
    expr: Optional[Node]

@dataclass
class Assignment(Node):
    name: str
    op: str          # "=", "+=", "-=", "*=", "/="
    expr: Node

@dataclass
class IncDec(Node):
    name: str
    op: str          # "++" or "--"

@dataclass
class Print(Node):
    expr: Node

@dataclass
class Input(Node):
    name: str

@dataclass
class Literal(Node):
    value: object
    dtype: str

@dataclass
class BinOp(Node):
    left: Node
    op: str
    right: Node

@dataclass
class UnaryOp(Node):
    op: str          # "-" or "!"
    operand: Node

@dataclass
class Identifier(Node):
    name: str

@dataclass
class If(Node):
    branches: List[tuple]          # list of (condition, block); condition=None means else
    # branches = [(cond, block), (cond2, block2), ..., (None, else_block)]

@dataclass
class While(Node):
    cond: Node
    body: List[Node]

@dataclass
class For(Node):
    init: Optional[Node]
    cond: Optional[Node]
    post: Optional[Node]
    body: List[Node]

@dataclass
class FuncDef(Node):
    name: str
    params: List[tuple]            # [(type, name), ...]
    body: List[Node]
    ret_type: Optional[str]        # parsed return type if declared

@dataclass
class Return(Node):
    expr: Optional[Node]

@dataclass
class FuncCall(Node):
    name: str
    args: List[Node]

@dataclass
class Break(Node): pass

@dataclass
class Continue(Node): pass

# ── Parser ───────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    # ── helpers ──────────────────────────────────────────────────────────────

    def peek(self, offset=0):
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def consume(self, expected=None):
        tok = self.peek()
        if expected and tok.type != expected:
            raise ParseError(
                f"Expected {expected!r} but got {tok.type!r} ({tok.value!r}) "
                f"at line {tok.line}, col {tok.col}"
            )
        self.pos += 1
        return tok

    def match(self, *types):
        if self.peek().type in types:
            return self.consume()
        return None

    # ── top level ─────────────────────────────────────────────────────────────

    def parse(self):
        stmts = []
        while self.peek().type != "EOF":
            stmts.append(self.statement())
        return Program(stmts)

    # ── statements ────────────────────────────────────────────────────────────

    TYPE_TOKENS = ("INT", "FLOAT", "STRING", "BOOL")

    def statement(self):
        t = self.peek()

        if t.type in self.TYPE_TOKENS:
            return self.var_decl()

        if t.type == "ID":
            next_type = self.peek(1).type
            if next_type == "LPAREN":
                return self.func_call_stmt()
            if next_type in ("INC", "DEC"):
                return self.incdec_stmt()
            return self.assignment()

        if t.type == "PRINT":   return self.print_stmt()
        if t.type == "INPUT":   return self.input_stmt()
        if t.type == "IF":      return self.if_stmt()
        if t.type == "WHILE":   return self.while_stmt()
        if t.type == "FOR":     return self.for_stmt()
        if t.type == "FUNC":    return self.func_def()
        if t.type == "RETURN":  return self.return_stmt()
        if t.type == "BREAK":   self.consume(); self.consume("SEMI"); return Break()
        if t.type == "CONTINUE":self.consume(); self.consume("SEMI"); return Continue()

        raise ParseError(f"Unexpected token {t.type!r} ({t.value!r}) at line {t.line}")

    def block(self):
        nodes = []
        self.consume("LBRACE")
        while self.peek().type != "RBRACE":
            nodes.append(self.statement())
        self.consume("RBRACE")
        return nodes

    def var_decl(self):
        type_tok = self.consume().type.lower()
        name = self.consume("ID").value
        expr = None
        if self.peek().type == "OP" and self.peek().value == "=":
            self.consume("OP")
            expr = self.expression()
        self.consume("SEMI")
        return VarDecl(type_tok, name, expr)

    def assignment(self):
        name = self.consume("ID").value
        tok = self.peek()
        # compound assignment: +=  -=  *=  /=  or plain =
        if tok.type == "OP" and tok.value in ("=", "+=", "-=", "*=", "/="):
            op = self.consume("OP").value
            expr = self.expression()
            self.consume("SEMI")
            return Assignment(name, op, expr)
        raise ParseError(f"Invalid assignment for {name!r} at line {tok.line}")

    def incdec_stmt(self):
        name = self.consume("ID").value
        op   = self.consume().value   # INC or DEC token
        self.consume("SEMI")
        return IncDec(name, op)

    def print_stmt(self):
        self.consume("PRINT")
        self.consume("LPAREN")
        expr = self.expression()
        self.consume("RPAREN")
        self.consume("SEMI")
        return Print(expr)

    def input_stmt(self):
        self.consume("INPUT")
        self.consume("LPAREN")
        name = self.consume("ID").value
        self.consume("RPAREN")
        self.consume("SEMI")
        return Input(name)

    def if_stmt(self):
        """Supports if / elif chains / else."""
        self.consume("IF")
        self.consume("LPAREN")
        cond = self.expression()
        self.consume("RPAREN")
        then_block = self.block()
        branches = [(cond, then_block)]

        while self.peek().type == "ELIF":
            self.consume("ELIF")
            self.consume("LPAREN")
            elif_cond = self.expression()
            self.consume("RPAREN")
            elif_block = self.block()
            branches.append((elif_cond, elif_block))

        if self.peek().type == "ELSE":
            self.consume("ELSE")
            else_block = self.block()
            branches.append((None, else_block))   # None cond = else

        return If(branches)

    def while_stmt(self):
        self.consume("WHILE")
        self.consume("LPAREN")
        cond = self.expression()
        self.consume("RPAREN")
        body = self.block()
        return While(cond, body)

    def for_stmt(self):
        self.consume("FOR")
        self.consume("LPAREN")

        # init
        init = None
        if self.peek().type != "SEMI":
            if self.peek().type in self.TYPE_TOKENS:
                init = self.var_decl()
            elif self.peek(1).type in ("INC", "DEC"):
                init = self.incdec_stmt()
            else:
                init = self.assignment()
        else:
            self.consume("SEMI")

        # cond
        cond = None
        if self.peek().type != "SEMI":
            cond = self.expression()
        self.consume("SEMI")

        # post-step: assignment or i++ / i--
        post = None
        if self.peek().type != "RPAREN":
            if self.peek(1).type in ("INC", "DEC"):
                name = self.consume("ID").value
                op   = self.consume().value
                post = IncDec(name, op)
            else:
                name = self.consume("ID").value
                tok  = self.peek()
                if tok.type == "OP" and tok.value in ("=", "+=", "-=", "*=", "/="):
                    op   = self.consume("OP").value
                    expr = self.expression()
                    post = Assignment(name, op, expr)
                else:
                    raise ParseError(f"Invalid for-loop post-step at line {tok.line}")

        self.consume("RPAREN")
        body = self.block()
        return For(init, cond, post, body)

    def func_def(self):
        self.consume("FUNC")
        # optional return-type annotation: func int add(...)
        ret_type = None
        if self.peek().type in self.TYPE_TOKENS:
            ret_type = self.consume().type.lower()
        name = self.consume("ID").value
        self.consume("LPAREN")
        params = []
        if self.peek().type != "RPAREN":
            while True:
                ptype = self.consume().type.lower()
                pname = self.consume("ID").value
                params.append((ptype, pname))
                if self.peek().type == "COMMA":
                    self.consume("COMMA")
                else:
                    break
        self.consume("RPAREN")
        body = self.block()
        return FuncDef(name, params, body, ret_type)

    def return_stmt(self):
        self.consume("RETURN")
        expr = None
        if self.peek().type != "SEMI":
            expr = self.expression()
        self.consume("SEMI")
        return Return(expr)

    def func_call_stmt(self):
        call = self.func_call()
        self.consume("SEMI")
        return call

    def func_call(self):
        name = self.consume("ID").value
        self.consume("LPAREN")
        args = []
        if self.peek().type != "RPAREN":
            while True:
                args.append(self.expression())
                if self.peek().type == "COMMA":
                    self.consume("COMMA")
                else:
                    break
        self.consume("RPAREN")
        return FuncCall(name, args)

    # ── expressions (recursive descent, precedence climbing) ─────────────────

    def expression(self):
        return self.logic_or()

    def logic_or(self):
        node = self.logic_and()
        while self.peek().type == "OP" and self.peek().value == "||":
            op = self.consume("OP").value
            node = BinOp(node, op, self.logic_and())
        return node

    def logic_and(self):
        node = self.equality()
        while self.peek().type == "OP" and self.peek().value == "&&":
            op = self.consume("OP").value
            node = BinOp(node, op, self.equality())
        return node

    def equality(self):
        node = self.relational()
        while self.peek().type == "OP" and self.peek().value in ("==", "!="):
            op = self.consume("OP").value
            node = BinOp(node, op, self.relational())
        return node

    def relational(self):
        node = self.term()
        while self.peek().type == "OP" and self.peek().value in ("<", ">", "<=", ">="):
            op = self.consume("OP").value
            node = BinOp(node, op, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek().type == "OP" and self.peek().value in ("+", "-"):
            op = self.consume("OP").value
            node = BinOp(node, op, self.factor())
        return node

    def factor(self):
        node = self.unary()
        while self.peek().type == "OP" and self.peek().value in ("*", "/", "%"):
            op = self.consume("OP").value
            node = BinOp(node, op, self.unary())
        return node

    def unary(self):
        if self.peek().type == "OP" and self.peek().value == "-":
            self.consume("OP")
            return UnaryOp("-", self.unary())
        if self.peek().type == "NOT":
            self.consume("NOT")
            return UnaryOp("!", self.unary())
        return self.primary()

    def primary(self):
        tok = self.peek()
        if tok.type == "INT":
            return Literal(int(self.consume("INT").value), "int")
        if tok.type == "FLOAT":
            return Literal(float(self.consume("FLOAT").value), "float")
        if tok.type == "STRING":
            return Literal(self.consume("STRING").value, "string")
        if tok.type == "TRUE":
            self.consume("TRUE"); return Literal(True, "bool")
        if tok.type == "FALSE":
            self.consume("FALSE"); return Literal(False, "bool")
        if tok.type == "ID":
            if self.peek(1).type == "LPAREN":
                return self.func_call()
            return Identifier(self.consume("ID").value)
        if tok.type == "LPAREN":
            self.consume("LPAREN")
            e = self.expression()
            self.consume("RPAREN")
            return e
        raise ParseError(f"Unexpected token {tok.type!r} ({tok.value!r}) at line {tok.line}")
