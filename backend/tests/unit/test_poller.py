from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from helio.ingestion.poller import detect_gaps


@pytest.mark.asyncio
async def test_detect_gaps_returns_missing_dates():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[date(2024, 4, 1), date(2024, 4, 3)])
                )
            )
        )
    )

    gaps = await detect_gaps(
        session=mock_session,
        system_id=1,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 4),
    )
    assert date(2024, 4, 2) in gaps
    assert date(2024, 4, 4) in gaps
    assert date(2024, 4, 1) not in gaps
    assert date(2024, 4, 3) not in gaps


@pytest.mark.asyncio
async def test_detect_gaps_no_gaps():
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(
                        return_value=[
                            date(2024, 4, 1),
                            date(2024, 4, 2),
                            date(2024, 4, 3),
                        ]
                    )
                )
            )
        )
    )

    gaps = await detect_gaps(
        session=mock_session,
        system_id=1,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 3),
    )
    assert gaps == []
