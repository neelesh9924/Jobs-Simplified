import shutil
import subprocess
import tempfile
from pathlib import Path

from .latex_resume import render_latex


class TectonicNotInstalled(RuntimeError):
    pass


class LatexCompileError(RuntimeError):
    pass


def _tectonic_bin() -> str:
    path = shutil.which("tectonic")
    if not path:
        raise TectonicNotInstalled(
            "tectonic not found on PATH. Install it with: brew install tectonic"
        )
    return path


def compile_resume_pdf(resume: dict) -> bytes:
    return compile_latex(render_latex(resume))


def compile_latex(tex: str) -> bytes:
    tectonic = _tectonic_bin()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tex_file = tmp_path / "resume.tex"
        tex_file.write_text(tex, encoding="utf-8")

        proc = subprocess.run(
            [tectonic, "--chatter", "minimal", "--outdir", str(tmp_path), str(tex_file)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise LatexCompileError(proc.stderr or proc.stdout or "tectonic failed")

        pdf_file = tmp_path / "resume.pdf"
        if not pdf_file.exists():
            raise LatexCompileError("tectonic produced no PDF")
        return pdf_file.read_bytes()
