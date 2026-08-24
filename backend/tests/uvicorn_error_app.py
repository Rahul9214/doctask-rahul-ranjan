from app.main import create_app

app = create_app()


@app.get("/unexpected")
async def unexpected() -> None:
    raise RuntimeError(
        "SECRET_SENTINEL_DO_NOT_LEAK | "
        "SOURCE_TEXT_SENTINEL_DO_NOT_LEAK | "
        "postgresql://credential-sentinel"
    )
