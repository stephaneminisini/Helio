from helio.db.models import (
    DailySummary,
    EnergyInterval,
    Irradiance,
    MonthlySummary,
    PollLog,
    System,
)


def test_system_tablename():
    assert System.__tablename__ == "systems"


def test_energy_interval_tablename():
    assert EnergyInterval.__tablename__ == "energy_intervals"


def test_daily_summary_tablename():
    assert DailySummary.__tablename__ == "daily_summaries"


def test_monthly_summary_tablename():
    assert MonthlySummary.__tablename__ == "monthly_summaries"


def test_irradiance_tablename():
    assert Irradiance.__tablename__ == "irradiance"


def test_poll_log_tablename():
    assert PollLog.__tablename__ == "poll_log"
