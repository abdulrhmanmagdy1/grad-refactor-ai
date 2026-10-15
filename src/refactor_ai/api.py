from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

from refactor_ai import __version__
from refactor_ai.analysis import AnalysisResult, analyze

app = FastAPI(
    title="Python Refactoring Foundation",
    version=__version__,
    description="Foundation API: static analysis only. No LLM, code execution, or refactoring yet.",
)


class AnalysisRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20000)

    @field_validator("code")
    @classmethod
    def require_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("code must not be blank")
        return value


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__, "mode": "scaffold"}


@app.post("/api/v1/analyze", response_model=AnalysisResult)
def analyze_code(request: AnalysisRequest) -> AnalysisResult:
    return analyze(request.code)
