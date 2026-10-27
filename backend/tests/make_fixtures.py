"""Builds tests/fixtures/synthetic_resume.pdf. The person and details are invented,
so tests never depend on a real resume. Run: python tests/make_fixtures.py"""

from pathlib import Path

from fpdf import FPDF

LINES = [
    ("B", 16, "ALEX EXAMPLE"),
    ("", 11, "M.Sc. Computer Science student, Example University"),
    ("B", 12, "EXPERIENCE"),
    ("", 11, "Software Engineering Intern, Acme Robotics (2024)"),
    ("", 11, "- Implemented a thread-safe message queue in C++17 used by three sensor services."),
    ("", 11, "- Wrote Python scripts to automate log analysis, cutting triage time by 30%."),
    ("", 11, "- Added GoogleTest unit tests and a GitLab CI pipeline stage for the module."),
    ("B", 12, "PROJECTS"),
    ("", 11, "Traffic Dashboard: React and TypeScript dashboard visualising live sensor data."),
    ("B", 12, "SKILLS"),
    ("", 11, "Languages: C++, Python, Java, TypeScript"),
    ("", 11, "Tools: Git, CMake, Docker, GitLab CI"),
]


def build(path: Path) -> None:
    pdf = FPDF()
    pdf.add_page()
    for style, size, text in LINES:
        pdf.set_font("Helvetica", style, size)
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


if __name__ == "__main__":
    build(Path(__file__).parent / "fixtures" / "synthetic_resume.pdf")
