import typer
from sqlalchemy import func, select

from app.core.logging import configure_logging
from app.db.models import Event, RaceSession, Season
from app.db.session import SessionLocal
from app.ingestion.service import IngestionError, RaceIngestionService

app = typer.Typer(help="Download and normalize historical race data.")


@app.callback()
def main() -> None:
    """Apex Strategist historical data ingestion commands."""


@app.command("ingest-race")
def ingest_race(
    year: int = typer.Option(..., min=2018, max=2100, help="Formula 1 season year"),
    event: str = typer.Option(..., help="Event name or FastF1 event selector"),
    force: bool = typer.Option(False, help="Replace normalized data when already ingested"),
) -> None:
    configure_logging()
    with SessionLocal() as db:
        try:
            result = RaceIngestionService(db).ingest(year, event, force)
        except IngestionError as exc:
            typer.echo(f"Ingestion failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"{result.status}: {result.message} session_id={result.session_id}")


@app.command("ingest-season")
def ingest_season(
    year: int = typer.Option(..., min=2018, max=2100, help="Formula 1 season year"),
    force: bool = typer.Option(False, help="Replace races that are already ingested"),
) -> None:
    """Download and normalize every Grand Prix in a season."""
    configure_logging()
    with SessionLocal() as db:
        service = RaceIngestionService(db)
        try:
            races = service.client.list_races(year)
        except Exception as exc:
            typer.echo(f"Could not load the {year} calendar: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(f"Found {len(races)} championship races for {year}.")
        failures: list[tuple[str, str]] = []
        for index, race in enumerate(races, start=1):
            label = f"round {race.round_number}: {race.event_name}"
            typer.echo(f"[{index}/{len(races)}] Ingesting {label}...")
            try:
                result = service.ingest(year, race.round_number, force)
            except IngestionError as exc:
                failures.append((label, str(exc)))
                typer.echo(f"[{index}/{len(races)}] Failed {label}: {exc}", err=True)
                continue
            typer.echo(
                f"[{index}/{len(races)}] {result.status}: {result.message} "
                f"session_id={result.session_id}"
            )

    completed = len(races) - len(failures)
    typer.echo(f"Season ingestion finished: {completed}/{len(races)} races available.")
    if failures:
        typer.echo("Failed races:", err=True)
        for label, error in failures:
            typer.echo(f"- {label}: {error}", err=True)
        raise typer.Exit(code=1)


@app.command("backfill-entry-teams")
def backfill_entry_teams(
    year: int | None = typer.Option(None, min=2018, max=2100),
    event: str | None = typer.Option(None, help="Optional case-insensitive event-name filter"),
) -> None:
    """Backfill race-specific teams from FastF1 results without replacing laps."""
    configure_logging()
    with SessionLocal() as db:
        service = RaceIngestionService(db)
        query = (
            select(RaceSession, Event, Season)
            .join(Event, Event.id == RaceSession.event_id)
            .join(Season, Season.id == Event.season_id)
            .where(
                RaceSession.session_type == "RACE",
                RaceSession.ingestion_status == "complete",
            )
            .order_by(Season.year, Event.round_number)
        )
        if year is not None:
            query = query.where(Season.year == year)
        if event:
            query = query.where(func.lower(Event.event_name).contains(event.casefold()))
        sessions = list(db.execute(query).all())
        if not sessions:
            raise typer.BadParameter("No ingested race sessions match the requested filter")
        total_entries = 0
        failures: list[str] = []
        for index, (session, race, season) in enumerate(sessions, start=1):
            label = f"{season.year} round {race.round_number} · {race.event_name}"
            try:
                source = service.client.load_race_results(season.year, race.round_number)
                updated = service.backfill_entry_teams(session.id, source)
                db.commit()
                total_entries += updated
                typer.echo(f"[{index}/{len(sessions)}] {label}: {updated} entries")
            except Exception as exc:
                db.rollback()
                failures.append(f"{label}: {exc}")
                typer.echo(f"[{index}/{len(sessions)}] {label}: failed", err=True)
        typer.echo(
            f"Team backfill finished: {total_entries} entries across "
            f"{len(sessions) - len(failures)}/{len(sessions)} races."
        )
        if failures:
            for failure in failures:
                typer.echo(f"- {failure}", err=True)
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
