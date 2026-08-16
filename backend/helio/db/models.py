from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


class System(Base):
    """Represents a solar energy system registered in the platform.

    Attributes:
        id: Primary key.
        enphase_system_id: Unique external identifier from Enphase.
        name: Optional human-readable name for the system.
        location: Optional textual location description.
        latitude: Geographic latitude.
        longitude: Geographic longitude.
        system_size_kw: Installed capacity in kilowatts.
        panel_count: Number of panels installed.
        panel_wattage_w: Wattage per panel.
        manufacturer: Panel manufacturer name.
        install_date: Date the system was installed.
        tilt_angle_deg: Tilt angle of the panels in degrees.
        azimuth_deg: Azimuth orientation of the panels in degrees.
        degradation_rate: Annual degradation rate (default 0.5).
        irradiance_source: Source identifier for irradiance data (default "nasa").
        enphase_access_token: Fernet-encrypted Enphase OAuth access token.
        enphase_refresh_token: Fernet-encrypted Enphase OAuth refresh token.
        token_updated_at: Timestamp of the last successful token rotation.
        created_at: Timestamp when the record was created.
        updated_at: Timestamp when the record was last updated.
        intervals: Related energy interval records.
        daily_summaries: Related daily summary records.
        monthly_summaries: Related monthly summary records.
        irradiance_records: Related irradiance records.
        poll_logs: Related poll log records.
    """

    __tablename__ = "systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enphase_system_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(256))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    system_size_kw: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    panel_count: Mapped[int | None] = mapped_column(Integer)
    panel_wattage_w: Mapped[int | None] = mapped_column(Integer)
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    install_date: Mapped[date] = mapped_column(Date, nullable=False)
    tilt_angle_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    azimuth_deg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    degradation_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), default=Decimal("0.5"), server_default="0.500"
    )
    irradiance_source: Mapped[str] = mapped_column(
        String(32), default="nasa", server_default="nasa"
    )
    # Ciphertext, not plaintext: written only via helio.ingestion.tokens so the
    # Fernet encryption cannot be bypassed. Text because Fernet output grows
    # with the token length and has no useful upper bound.
    enphase_access_token: Mapped[str | None] = mapped_column(Text)
    enphase_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    intervals: Mapped[list["EnergyInterval"]] = relationship(back_populates="system")
    daily_summaries: Mapped[list["DailySummary"]] = relationship(
        back_populates="system"
    )
    monthly_summaries: Mapped[list["MonthlySummary"]] = relationship(
        back_populates="system"
    )
    irradiance_records: Mapped[list["Irradiance"]] = relationship(
        back_populates="system"
    )
    poll_logs: Mapped[list["PollLog"]] = relationship(back_populates="system")


class EnergyInterval(Base):
    """Represents a single energy production/consumption interval (e.g. 15 minutes).

    Attributes:
        id: Primary key.
        system_id: Foreign key referencing the parent system.
        interval_start: Start timestamp of the interval (timezone-aware).
        duration_seconds: Duration of the interval in seconds (default 900).
        production_wh: Energy produced during the interval in watt-hours.
        consumption_wh: Energy consumed during the interval in watt-hours.
        net_wh: Net energy (production minus consumption) in watt-hours.
        created_at: Timestamp when the record was created.
        system: Related System instance.
    """

    __tablename__ = "energy_intervals"
    __table_args__ = (
        UniqueConstraint("system_id", "interval_start"),
        Index("idx_intervals_system_start", "system_id", "interval_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    interval_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=900, server_default="900"
    )
    production_wh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    consumption_wh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    net_wh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    system: Mapped["System"] = relationship(back_populates="intervals")


class DailySummary(Base):
    """Aggregated daily production and consumption statistics for a system.

    Attributes:
        id: Primary key.
        system_id: Foreign key referencing the parent system.
        day: The calendar date this summary covers.
        production_kwh: Total energy produced in kilowatt-hours.
        consumption_kwh: Total energy consumed in kilowatt-hours.
        peak_power_w: Peak instantaneous power recorded in watts.
        peak_power_at: Timestamp when peak power occurred.
        interval_count: Number of intervals included in the summary.
        is_complete: Whether all expected intervals for the day are present.
        created_at: Timestamp when the record was created.
        updated_at: Timestamp when the record was last updated.
        system: Related System instance.
    """

    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("system_id", "day"),
        Index("idx_daily_system_day", "system_id", "day"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    production_kwh: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    consumption_kwh: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    peak_power_w: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    peak_power_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_count: Mapped[int | None] = mapped_column(Integer)
    is_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    system: Mapped["System"] = relationship(back_populates="daily_summaries")


class MonthlySummary(Base):
    """Aggregated monthly production statistics with performance analysis.

    Attributes:
        id: Primary key.
        system_id: Foreign key referencing the parent system.
        month: The first day of the month this summary covers.
        production_kwh: Total energy produced in kilowatt-hours.
        theoretical_kwh: Theoretical maximum production based on irradiance.
        performance_ratio: Actual vs theoretical performance ratio.
        expected_pr: Expected performance ratio given system age and degradation.
        is_anomaly: Whether this month was flagged as anomalous.
        anomaly_reason: Human-readable explanation of the anomaly if flagged.
        created_at: Timestamp when the record was created.
        updated_at: Timestamp when the record was last updated.
        system: Related System instance.
    """

    __tablename__ = "monthly_summaries"
    __table_args__ = (
        UniqueConstraint("system_id", "month"),
        Index("idx_monthly_system_month", "system_id", "month"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    production_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    theoretical_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    performance_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    expected_pr: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    is_anomaly: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    anomaly_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    system: Mapped["System"] = relationship(back_populates="monthly_summaries")


class Irradiance(Base):
    """Daily solar irradiance measurements for a system location.

    Attributes:
        id: Primary key.
        system_id: Foreign key referencing the parent system.
        day: The calendar date of the measurement.
        ghi_kwh_m2: Global Horizontal Irradiance in kWh/m2.
        dni_kwh_m2: Direct Normal Irradiance in kWh/m2.
        poa_kwh_m2: Plane of Array Irradiance in kWh/m2.
        source: Data source identifier that supplied this row (e.g. "nasa").
        created_at: Timestamp when the record was created.
        system: Related System instance.
    """

    __tablename__ = "irradiance"
    __table_args__ = (UniqueConstraint("system_id", "day", "source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int] = mapped_column(ForeignKey("systems.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    ghi_kwh_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    dni_kwh_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    poa_kwh_m2: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    system: Mapped["System"] = relationship(back_populates="irradiance_records")


class PollLog(Base):
    """Audit log for data polling operations against external APIs.

    Attributes:
        id: Primary key.
        system_id: Optional foreign key referencing the polled system.
        poll_type: Identifier for the type of polling operation performed.
        started_at: Timestamp when the poll operation started.
        completed_at: Timestamp when the poll operation completed.
        status: Final status of the operation (e.g. "success", "error").
        records_fetched: Number of records retrieved from the external API.
        records_inserted: Number of new records persisted to the database.
        error_message: Error details if the operation failed.
        date_range_start: Start of the date range requested.
        date_range_end: End of the date range requested.
        system: Related System instance (optional).
    """

    __tablename__ = "poll_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    system_id: Mapped[int | None] = mapped_column(ForeignKey("systems.id"))
    poll_type: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(16))
    records_fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_inserted: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    date_range_start: Mapped[date | None] = mapped_column(Date)
    date_range_end: Mapped[date | None] = mapped_column(Date)

    system: Mapped["System | None"] = relationship(back_populates="poll_logs")
