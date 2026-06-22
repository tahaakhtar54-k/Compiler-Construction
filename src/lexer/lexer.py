import re
from dataclasses import dataclass

@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int

class LexerError(Exception):
    pass

class Lexer:
    KEYWORDS = {
        "if", "else", "elif", "while", "for", "print", "input",
        "func", "return", "true", "false", "int", "float", "string",
        "bool", "break", "continue"
    }

    SPEC = [
        ("COMMENT_ML", r'/\*[\s\S]*?\*/'),
        ("COMMENT_SL", r'//[^\n]*'),
        ("STRING",     r'"(?:[^"\\]|\\.)*"'),
        ("FLOAT",      r'\d+\.\d+'),
        ("INT",        r'\d+'),
        ("ID",         r'[A-Za-z_][A-Za-z0-9_]*'),
        ("OP",         r'==|!=|<=|>=|&&|\|\||!|\+\+|--|[+\-*/%<>]=?|='),
        ("SEMI",       r';'),
        ("LPAREN",     r'\('),
        ("RPAREN",     r'\)'),
        ("LBRACE",     r'\{'),
        ("RBRACE",     r'\}'),
        ("LBRACKET",   r'\['),
        ("RBRACKET",   r'\]'),
        ("COMMA",      r','),
        ("NEWLINE",    r'\n'),
        ("SKIP",       r'[ \t\r]+'),
        ("MISMATCH",   r'.'),
    ]

    def __init__(self, code):
        self.code = code
        self.line = 1
        self.col  = 1
        self.regex = re.compile(
            "|".join(f"(?P<{n}>{p})" for n, p in Lexer.SPEC),
            re.DOTALL
        )

    def _unescape(self, s):
        """Process escape sequences inside a quoted string literal."""
        inner = s[1:-1]  # strip surrounding quotes
        result = []
        i = 0
        while i < len(inner):
            if inner[i] == '\\' and i + 1 < len(inner):
                c = inner[i + 1]
                escape_map = {'n': '\n', 't': '\t', 'r': '\r',
                              '"': '"',  '\\': '\\'}
                result.append(escape_map.get(c, c))
                i += 2
            else:
                result.append(inner[i])
                i += 1
        return ''.join(result)

    def tokenize(self):
        tokens = []
        for m in self.regex.finditer(self.code):
            kind     = m.lastgroup
            val      = m.group()
            tok_line = self.line
            tok_col  = self.col

            # --- skip / structural ---
            if kind in ("COMMENT_SL", "COMMENT_ML"):
                newlines = val.count('\n')
                if newlines:
                    self.line += newlines
                    self.col = len(val) - val.rfind('\n')
                else:
                    self.col += len(val)
                continue

            if kind == "NEWLINE":
                self.line += 1
                self.col = 1
                continue

            if kind == "SKIP":
                self.col += len(val)
                continue

            if kind == "MISMATCH":
                raise LexerError(
                    f"Unexpected character {val!r} at line {tok_line}, col {tok_col}"
                )

            # --- value processing ---
            if kind == "STRING":
                val = self._unescape(val)

            elif kind == "ID":
                if val in Lexer.KEYWORDS:
                    kind = val.upper()

            elif kind == "OP":
                if val == "++":
                    kind = "INC"
                elif val == "--":
                    kind = "DEC"
                elif val == "!":
                    kind = "NOT"

            tokens.append(Token(kind, val, tok_line, tok_col))
            self.col += len(m.group())

        tokens.append(Token("EOF", "", self.line, self.col))
        return tokens


if __name__ == "__main__":
    code = r'''
// single-line comment
/* multi
   line comment */
int x = 5;
string msg = "hello\nworld";
bool flag = true;
if (!flag) { print(x); }
for (int i = 0; i < 3; i++) { print(i); }
'''
    lx = Lexer(code)
    for t in lx.tokenize():
        print(t)
