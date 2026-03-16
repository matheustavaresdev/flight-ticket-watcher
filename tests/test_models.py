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
            "min_trip_days",
            "active",
            "retry_count",
            "needs_attention",
            "created_at",
            "updated_at",
        }

    def test_indexes(self):
        index_names = {idx.name for idx in SearchConfig.__table__.indexes}
        assert "ix_search_configs_origin_dest" in index_names

    def test_check_constraints(self):
        constraint_names = {
            c.name
            for c in SearchConfig.__table__.constraints
            if hasattr(c, "name") and c.name is not None
        }
        assert "ck_search_configs_min_trip_days_positive" in constraint_names
        assert "ck_search_configs_min_le_max_trip_days" in constraint_names


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
        assert "ix_scan_runs_config_status" in index_names
        assert "ix_scan_runs_config_id" not in index_names
        assert "ix_scan_runs_status" not in index_names


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
        assert "ix_price_snapshots_route_date_brand" in index_names
        assert "ix_price_snapshots_date_fetched" in index_names


class TestEnums:
    def test_scan_status_values(self):
        assert ScanStatus.RUNNING.value == "running"
        assert ScanStatus.COMPLETED.value == "completed"
        assert ScanStatus.FAILED.value == "failed"

    def test_search_type_values(self):
        assert SearchType.ONEWAY.value == "oneway"
        assert SearchType.ROUNDTRIP.value == "roundtrip"


class TestSearchResult:
    def test_success_sets_ok_and_data(self):
        from flight_watcher.models import SearchResult

        result = SearchResult.success(["a", "b"])

        assert result.ok is True
        assert result.data == ["a", "b"]
        assert result.error is None
        assert result.error_category is None

    def test_failure_sets_ok_false_and_error(self):
        from flight_watcher.errors import ErrorCategory
        from flight_watcher.models import SearchResult

        result = SearchResult.failure(
            "network timeout",
            error_category=ErrorCategory.NETWORK_ERROR,
            hint="retry later",
        )

        assert result.ok is False
        assert result.data is None
        assert result.error == "network timeout"
        assert result.error_category == ErrorCategory.NETWORK_ERROR
        assert result.hint == "retry later"

    def test_success_with_none_data(self):
        from flight_watcher.models import SearchResult

        r = SearchResult.success(None)

        assert r.ok is True
        assert r.data is None
        assert r.error is None
        assert r.error_category is None

    def test_duration_sec_propagated(self):
        from flight_watcher.models import SearchResult

        r1 = SearchResult.success([], duration_sec=1.23)
        r2 = SearchResult.failure("err", duration_sec=4.56)

        assert r1.duration_sec == 1.23
        assert r2.duration_sec == 4.56


class TestPriceAlert:
    def test_tablename(self):
        from flight_watcher.models import PriceAlert

        assert PriceAlert.__tablename__ == "price_alerts"

    def test_columns_exist(self):
        from flight_watcher.models import PriceAlert

        cols = {c.name for c in PriceAlert.__table__.columns}
        assert cols == {
            "id",
            "search_config_id",
            "origin",
            "destination",
            "flight_date",
            "airline",
            "brand",
            "previous_low_price",
            "new_price",
            "price_drop_abs",
            "alert_type",
            "sent_to",
            "sent_at",
            "created_at",
        }

    def test_fk_references_search_configs(self):
        from flight_watcher.models import PriceAlert

        fk = next(iter(PriceAlert.__table__.c.search_config_id.foreign_keys))
        assert fk.target_fullname == "search_configs.id"

    def test_indexes(self):
        from flight_watcher.models import PriceAlert

        index_names = {idx.name for idx in PriceAlert.__table__.indexes}
        assert "ix_price_alerts_route_date" in index_names


class TestAlertType:
    def test_alert_type_values(self):
        from flight_watcher.models import AlertType

        assert AlertType.NEW_LOW.value == "new_low"
        assert AlertType.THRESHOLD.value == "threshold"
