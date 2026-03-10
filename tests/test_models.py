from flight_watcher.models import (
    PriceSnapshot,
    ScanRun,
    ScanStatus,
    SearchConfig,
    SearchType,
)


class TestSearchConfig:
    def test_tablename(self):
        assert SearchConfig.__tablename__ == "search_configs"

    def test_columns_exist(self):
        cols = {c.name for c in SearchConfig.__table__.columns}
        assert cols == {
            "id",
            "origin",
            "destination",
            "must_arrive_by",
            "must_stay_until",
            "max_trip_days",
            "active",
            "created_at",
            "updated_at",
        }

    def test_indexes(self):
        index_names = {idx.name for idx in SearchConfig.__table__.indexes}
        assert "ix_search_configs_origin_dest" in index_names


class TestScanRun:
    def test_tablename(self):
        assert ScanRun.__tablename__ == "scan_runs"

    def test_columns_exist(self):
        cols = {c.name for c in ScanRun.__table__.columns}
        assert cols == {
            "id",
            "search_config_id",
            "started_at",
            "completed_at",
            "status",
            "last_successful_date",
            "error_message",
        }

    def test_fk_references_search_configs(self):
        fk = next(iter(ScanRun.__table__.c.search_config_id.foreign_keys))
        assert fk.target_fullname == "search_configs.id"

    def test_indexes(self):
        index_names = {idx.name for idx in ScanRun.__table__.indexes}
        assert "ix_scan_runs_config_id" in index_names
        assert "ix_scan_runs_status" in index_names


class TestPriceSnapshot:
    def test_tablename(self):
        assert PriceSnapshot.__tablename__ == "price_snapshots"

    def test_columns_exist(self):
        cols = {c.name for c in PriceSnapshot.__table__.columns}
        assert cols == {
            "id",
            "scan_run_id",
            "origin",
            "destination",
            "flight_date",
            "flight_code",
            "departure_time",
            "arrival_time",
            "duration_min",
            "stops",
            "brand",
            "price",
            "currency",
            "search_type",
            "fetched_at",
        }

    def test_fk_references_scan_runs(self):
        fk = next(iter(PriceSnapshot.__table__.c.scan_run_id.foreign_keys))
        assert fk.target_fullname == "scan_runs.id"

    def test_indexes(self):
        index_names = {idx.name for idx in PriceSnapshot.__table__.indexes}
        assert "ix_price_snapshots_run_id" in index_names
        assert "ix_price_snapshots_route_date" in index_names


class TestEnums:
    def test_scan_status_values(self):
        assert ScanStatus.RUNNING.value == "running"
        assert ScanStatus.COMPLETED.value == "completed"
        assert ScanStatus.FAILED.value == "failed"

    def test_search_type_values(self):
        assert SearchType.ONEWAY.value == "oneway"
        assert SearchType.ROUNDTRIP.value == "roundtrip"
