import sys
import pprint
from src.lexer.lexer     import Lexer
from src.parser.parser   import Parser
from src.semantic.semantic import SemanticAnalyzer
from src.ir.ir_generator  import IRGenerator
from src.optimizer.optimizer import IROptimizer
from src.vm.vm            import VM


def compile_and_run(code, show_ir=True):
    # ── Phase 1: Lexical Analysis ─────────────────────────────────────────────
    print("=" * 22 + " 1. LEXICAL ANALYSIS " + "=" * 22)
    lx     = Lexer(code)
    tokens = lx.tokenize()
    for t in tokens:
        print(t)

    # ── Phase 2: Syntax Analysis ──────────────────────────────────────────────
    print("\n" + "=" * 22 + " 2. SYNTAX ANALYSIS (AST) " + "=" * 22)
    p   = Parser(tokens)
    ast = p.parse()
    pprint.pprint(ast)

# ── Phase 3: Semantic Analysis ────────────────────────────────────────────────
    print("\n" + "=" * 22 + " 3. SEMANTIC ANALYSIS " + "=" * 22)
    sa = SemanticAnalyzer()
    try:
        sa.analyze(ast)
        print("Semantic Analysis: SUCCESS — types, scopes, and loops verified")
        sa.print_symbol_table()           # ← ADD THIS LINE
    except Exception as e:
        print(f"Semantic Analysis: FAILED — {e}")
        return

    # ── Phase 4: IR Generation ────────────────────────────────────────────────
    print("\n" + "=" * 22 + " 4. INTERMEDIATE REPRESENTATION " + "=" * 22)
    irgen = IRGenerator()
    irgen.gen(ast)
    print(f"Generated {len(irgen.code)} IR instructions:")
    for i, ins in enumerate(irgen.code):
        print(f"  {i:3}: {ins}")

    # ── Phase 5: Optimization ─────────────────────────────────────────────────
    print("\n" + "=" * 22 + " 5. OPTIMIZATION " + "=" * 22)
    opt          = IROptimizer(irgen.code)
    optimized_ir = opt.optimize()
    delta        = len(irgen.code) - len(optimized_ir)
    if delta > 0:
        print(f"Optimization: SUCCESS — reduced {len(irgen.code)} → {len(optimized_ir)} instructions ({delta} removed)")
    else:
        print(f"Optimization: COMPLETED — {len(optimized_ir)} instructions (nothing eliminated)")
    if show_ir:
        for i, ins in enumerate(optimized_ir):
            print(f"  {i:3}: {ins}")

    # ── Phase 6: VM Execution ─────────────────────────────────────────────────
    print("\n" + "=" * 22 + " 6. VM EXECUTION " + "=" * 22)
    vm = VM(optimized_ir)
    try:
        vm.run()
        print("\n[VM] Execution completed successfully.")
        if vm.globals:
            print("[VM] Final globals:", vm.globals)
    except Exception as e:
        print(f"[VM] Execution Error: {e}")


# ── sample program showcasing all features ──────────────────────────────

SAMPLE = """
// Demonstrate: comments, elif, break, continue, ++, !=, !, short-circuit

/* compute factorial using a for loop */
func int factorial(int n) {
    int result = 1;
    for (int i = 1; i <= n; i++) {
        result *= i;
    }
    return result;
}

/* check if a number is prime */
func bool is_prime(int n) {
    if (n < 2) {
        return false;
    }
    int i = 2;
    while (i <= n / 2) {
        int rem = n % i;
        if (rem == 0) {
            return false;
        }
        i++;
    }
    return true;
}

// --- main code ---
int x = 6;
int f = factorial(x);
print(f);           // 720

// elif chain
if (x < 0) {
    print("negative");
} elif (x == 0) {
    print("zero");
} elif (x < 10) {
    print("small positive");
} else {
    print("large positive");
}

// break inside while
int count = 0;
while (true) {
    count += 1;
    if (count == 3) {
        break;
    }
}
print(count);       // 3

// continue inside for
int sum = 0;
for (int i = 1; i <= 10; i++) {
    if (i % 2 == 0) {
        continue;
    }
    sum += i;       // sum of odd numbers 1..10
}
print(sum);         // 25

// unary NOT
bool flag = true;
bool inv  = !flag;
print(inv);         // false

// is_prime
print(is_prime(7));   // true
print(is_prime(9));   // false
"""


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            code = f.read()
        compile_and_run(code)
    else:
        compile_and_run(SAMPLE)
