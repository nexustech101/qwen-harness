"""Python AST parser for project graph construction."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from graph.models import CallSite, FileNode, GraphEdge, ImportInfo, ParameterInfo, SymbolNode


class ParsedFile:
    def __init__(
        self,
        file: FileNode,
        symbols: dict[str, SymbolNode],
        edges: list[GraphEdge],
        calls: list[CallSite],
    ) -> None:
        self.file = file
        self.symbols = symbols
        self.edges = edges
        self.calls = calls


def parse_python_file(path: Path, project_root: Path) -> ParsedFile:
    rel_path = path.relative_to(project_root).as_posix()
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    file_node = FileNode(
        path=rel_path,
        module=_module_name(rel_path),
        sha1=hashlib.sha1(raw).hexdigest(),
        line_count=text.count("\n") + (1 if text and not text.endswith("\n") else 0),
    )

    module_id = f"{rel_path}::<module>"
    symbols = {
        module_id: SymbolNode(
            id=module_id,
            name="<module>",
            qualname="<module>",
            kind="module",
            path=rel_path,
            line=1,
            end_line=max(file_node.line_count, 1),
        )
    }
    edges: list[GraphEdge] = []
    calls: list[CallSite] = []

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        file_node.syntax_error = f"{exc.msg} at line {exc.lineno}"
        return ParsedFile(file_node, symbols, edges, calls)

    visitor = _PythonGraphVisitor(rel_path, file_node.module, module_id, symbols, edges, calls)
    visitor.visit(tree)
    file_node.imports = visitor.imports
    return ParsedFile(file_node, symbols, edges, calls)


class _PythonGraphVisitor(ast.NodeVisitor):
    def __init__(
        self,
        rel_path: str,
        module: str,
        module_id: str,
        symbols: dict[str, SymbolNode],
        edges: list[GraphEdge],
        calls: list[CallSite],
    ) -> None:
        self.rel_path = rel_path
        self.module = module
        self.module_id = module_id
        self.symbols = symbols
        self.edges = edges
        self.calls = calls
        self.stack: list[SymbolNode] = [symbols[module_id]]
        self.imports: list[ImportInfo] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ImportInfo(
                    module=alias.name,
                    alias=alias.asname or alias.name.split(".")[0],
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            self.imports.append(
                ImportInfo(
                    module=module,
                    name=alias.name,
                    alias=alias.asname or alias.name,
                    level=node.level,
                    line=node.lineno,
                )
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_symbol(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_symbol(node, "method" if self._directly_inside_class() else "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_symbol(node, "async_method" if self._directly_inside_class() else "async_function")

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(
            CallSite(
                caller_id=self.stack[-1].id,
                expression=_call_expression(node.func),
                line=getattr(node, "lineno", 0),
                col=getattr(node, "col_offset", 0),
            )
        )
        self.generic_visit(node)

    def _add_symbol(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        kind: str,
    ) -> None:
        parent = self.stack[-1]
        parent_qual = "" if parent.qualname == "<module>" else parent.qualname
        qualname = f"{parent_qual}.{node.name}" if parent_qual else node.name
        symbol_id = f"{self.rel_path}::{qualname}"
        parameters: list[ParameterInfo] = []
        return_annotation = ""
        signature = node.name

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parameters = _parameters(node.args)
            return_annotation = _unparse(node.returns)
            signature = _signature(node.name, parameters, return_annotation)

        symbol = SymbolNode(
            id=symbol_id,
            name=node.name,
            qualname=qualname,
            kind=kind,
            path=self.rel_path,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            parameters=parameters,
            return_annotation=return_annotation,
            decorators=[_unparse(item) for item in node.decorator_list],
            doc_summary=_doc_summary(ast.get_docstring(node) or ""),
            parent_id=parent.id,
            signature=signature,
        )
        self.symbols[symbol_id] = symbol
        self.edges.append(GraphEdge(source=parent.id, target=symbol_id, kind="contains"))

        self.stack.append(symbol)
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    def _directly_inside_class(self) -> bool:
        return bool(self.stack and self.stack[-1].kind == "class")


def _module_name(rel_path: str) -> str:
    stem = rel_path.removesuffix(".py").replace("/", ".")
    return stem.removesuffix(".__init__")


def _parameters(args: ast.arguments) -> list[ParameterInfo]:
    params: list[ParameterInfo] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [""] * (len(positional) - len(args.defaults)) + [_unparse(d) for d in args.defaults]
    for arg, default in zip(positional, defaults):
        params.append(ParameterInfo(arg.arg, "positional", _unparse(arg.annotation), default))
    if args.vararg:
        params.append(ParameterInfo(args.vararg.arg, "vararg", _unparse(args.vararg.annotation)))
    for arg, default_node in zip(args.kwonlyargs, args.kw_defaults):
        params.append(ParameterInfo(arg.arg, "keyword_only", _unparse(arg.annotation), _unparse(default_node)))
    if args.kwarg:
        params.append(ParameterInfo(args.kwarg.arg, "kwarg", _unparse(args.kwarg.annotation)))
    return params


def _signature(name: str, params: list[ParameterInfo], returns: str) -> str:
    parts = []
    for param in params:
        prefix = "*" if param.kind == "vararg" else "**" if param.kind == "kwarg" else ""
        part = f"{prefix}{param.name}"
        if param.annotation:
            part += f": {param.annotation}"
        if param.default:
            part += f" = {param.default}"
        parts.append(part)
    signature = f"{name}({', '.join(parts)})"
    if returns:
        signature += f" -> {returns}"
    return signature


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _doc_summary(doc: str) -> str:
    for line in doc.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:240]
    return ""


def _call_expression(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_expression(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _call_expression(node.func)
    return _unparse(node) or "<unknown>"

