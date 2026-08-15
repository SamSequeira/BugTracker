"""Temporary helper — dumps the Java AST node tree for rule authoring."""
import sys, tempfile
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
from app.services.ast_generator import ASTGenerator

gen = ASTGenerator()
src = """\
public class Sample {
    int divide(int a, int b) { return a / b; }

    void nullDeref(String s) { int n = s.length(); }

    void openFile(String p) throws Exception {
        java.io.FileReader f = new java.io.FileReader(p);
        f.read();
    }

    void emptyCatch() {
        try { int x = 1; } catch (Exception e) {}
    }

    boolean strEq(String a, String b) { return a == b; }

    void arrAccess(int[] arr, int i) { int v = arr[i]; }

    void infiniteLoop() { while (true) { System.out.println(1); } }
}
"""
with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
    f.write(src); path = f.name

r = gen.generate_ast(path, 'Java')

def walk(node, depth=0):
    t = node['type']
    txt = repr(node.get('text', '')[:55])
    print(' ' * depth + t + '  |  ' + txt)
    for c in node.get('children', []):
        walk(c, depth + 2)

walk(r['ast'])
