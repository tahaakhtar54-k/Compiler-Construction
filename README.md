# SyntaxCraft

A from-scratch compiler and virtual machine for **`.min`** — a statically-typed, C-style mini-language. SyntaxCraft walks source code through all six classic compilation phases and executes the result on a custom register-based VM.

---

## Features

**Language (`*.min`)**

- Primitive types: `int`, `float`, `string`, `bool`
- Arithmetic (`+`, `-`, `*`, `/`, `%`) and compound assignment (`+=`, `-=`, `*=`, `/=`)
- Increment / decrement (`++`, `--`)
- Comparison (`==`, `!=`, `<`, `>`, `<=`, `>=`) and logical operators (`&&`, `||`, `!`) with short-circuit evaluation
- Control flow: `if` / `elif` / `else`, `while`, `for`
- Loop control: `break`, `continue`
- Typed functions with return values (`func <type> name(...)`)
- `print(expr)` and `input(var)` built-ins
- Single-line (`//`) and multi-line (`/* */`) comments
- String escape sequences (`\n`, `\t`, `\"`, `\\`)

**Compiler pipeline**

| Phase | Module | Description |
|---|---|---|
| 1 | Lexer | Regex-based tokeniser; strips comments, tracks line/col |
| 2 | Parser | Recursive-descent; builds a typed AST |
| 3 | Semantic analysis | Scope-aware type checker; validates loops, function arity/types, symbol table |
| 4 | IR generation | Lowers AST to a flat three-address instruction stream |
| 5 | Optimiser | Four passes: constant folding → copy propagation → dead-code elimination → unreachable-code removal |
| 6 | VM | Stack-based call frames; executes optimised IR directly |

---

## Project Structure

```
SyntaxCraft CC Project/
├── src/
│   ├── main.py               # Entry point — runs all six phases and prints diagnostics
│   ├── lexer/
│   │   └── lexer.py          # Lexer + Token dataclass
│   ├── parser/
│   │   └── parser.py         # Parser + all AST node dataclasses
│   ├── semantic/
│   │   └── semantic.py       # SemanticAnalyzer — type checker & symbol table
│   ├── ir/
│   │   └── ir_generator.py   # IRGenerator — AST → three-address IR
│   ├── optimizer/
│   │   └── optimizer.py      # IROptimizer — four-pass optimisation
│   ├── vm/
│   │   └── vm.py             # VM — executes IR; Frame-based call stack
│   └── gui.html              # Browser-based IDE / playground
└── tests/
    ├── sample1.min    # break / continue
    ├── sample2.min    # comments
    ├── sample3.min    # elif chains (grade classifier)
    ├── sample4.min    # functions: add, is_even, power
    ├── sample5.min    # boolean logic & short-circuit
    ├── sample6.min    # for / while loops
    ├── sample7.min    # if-else + function call
    ├── sample8.min    # factorial (while loop)
    ├── sample9.min    # arithmetic & modulo
    └── sample10.min   # constant folding demo
```

---

## Requirements

- Python 3.10 or later (developed with CPython 3.13)
- No third-party packages — standard library only

---

## Usage

**Run the built-in demo program**

```bash
python -m src.main
```

**Compile and run a `.min` file**

```bash
python -m src.main tests/sample4.min
```

**Browser playground**

Open `src/gui.html` in any modern browser. Type `.min` source in the editor and click **Run** to see the full compilation output inline.

---

## Language Quick Reference

```c
// Variables
int x = 42;
float pi = 3.14;
string msg = "hello\nworld";
bool flag = true;

// Functions
func int factorial(int n) {
    int result = 1;
    for (int i = 1; i <= n; i++) {
        result *= i;
    }
    return result;
}

// Control flow
if (x < 0) {
    print("negative");
} elif (x == 0) {
    print("zero");
} else {
    print("positive");
}

// Loops with break / continue
int sum = 0;
for (int i = 1; i <= 10; i++) {
    if (i % 2 == 0) { continue; }
    sum += i;
}
print(sum);   // 25

// Input
int n = 0;
input(n);
print(factorial(n));
```

---

## How the Compiler Works

### 1 — Lexer (`lexer.py`)
A single compiled regex pattern matches all token kinds in priority order. Comments and whitespace are consumed silently; keywords are promoted from `ID` tokens; `++`/`--`/`!` get dedicated token types. Line and column numbers are tracked for error messages.

### 2 — Parser (`parser.py`)
A hand-written recursive-descent parser converts the token stream into an AST composed of dataclass nodes (`VarDecl`, `BinOp`, `If`, `For`, `FuncDef`, …). Operator precedence is encoded in the call hierarchy: `logic_or → logic_and → equality → relational → term → factor → unary → primary`.

### 3 — Semantic Analyzer (`semantic.py`)
Two-pass analysis: function signatures are registered first so forward calls are valid. A scope stack handles shadowing; the global dict holds module-level variables. Type rules: `float` accepts `int` (widening); compound assignments require numeric operands; `&&`/`||` require `bool`; `break`/`continue` are validated against a loop-depth counter. A formatted symbol table is printed after analysis.

### 4 — IR Generator (`ir_generator.py`)
Produces a flat list of `Instr(op, args)` objects (three-address code). Function bodies are emitted before main code; a leading `JUMP MAIN1` skips them at startup. `&&`/`||` are lowered to branching sequences for short-circuit semantics. `break`/`continue` are resolved via label stacks.

**IR opcodes:** `LOAD_CONST`, `STORE`, `ALLOC`, `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `NEG`, `NOT`, `EQ`, `NE`, `LT`, `GT`, `LE`, `GE`, `JUMP`, `JUMP_IF_FALSE`, `LABEL`, `PRINT`, `INPUT`, `PUSH_ARG`, `CALL`, `POP_RET`, `RETVAL`, `RET`

### 5 — Optimiser (`optimizer.py`)
Four sequential passes over the IR:

1. **Constant folding** — arithmetic/comparison on statically-known values is replaced with a single `LOAD_CONST`.
2. **Copy propagation** — `STORE x t1` where `t1` is itself just another name is forwarded; `STORE x x` no-ops are dropped.
3. **Dead-code elimination** — temporary variables that are written but never read are removed.
4. **Unreachable-code removal** — instructions between an unconditional `JUMP`/`RET` and the next `LABEL` are dropped.

### 6 — VM (`vm.py`)
A `Frame` (local variable dict + return address) is pushed for each `CALL` and popped on `RET`. Return values travel through `ret_temp`; arguments travel through `arg_stack`. The global variable dict is separate from frame locals. Division-by-zero and stack-overflow (> 500 frames) raise `VMError`. Booleans are printed as lowercase `true`/`false`.

---

## Error Handling

| Layer | Exception | Example message |
|---|---|---|
| Lexer | `LexerError` | `Unexpected character '@' at line 3, col 7` |
| Parser | `ParseError` | `Expected 'RPAREN' but got 'SEMI' at line 5, col 12` |
| Semantic | `SemanticError` | `Type mismatch in 'x': declared 'int' but got 'bool'` |
| VM | `VMError` | `Runtime error: division by zero at instruction 42` |

---

## Optimiser Example

Input:

```c
int a = 10 + 5;
int b = a * 2;
print(b);
```

Before optimisation (excerpt):

```
LOAD_CONST t1 10
LOAD_CONST t2 5
ADD t3 t1 t2
STORE a t3
...
```

After constant folding + copy propagation:

```
LOAD_CONST t3 15
STORE a 15
LOAD_CONST t5 30
STORE b 30
PRINT b
```
