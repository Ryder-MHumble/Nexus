from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1 import reports
from app.api.v1.intel import personnel as personnel_api
from app.api.v1.intel import policy as policy_api
from app.api.v1.intel import tech_frontier as tech_frontier_api
from app.main import app
from app.schemas.report import ReportGenerateRequest
from app.services.intel.intel_store import IntelDataLoadError


def test_openapi_institutions_endpoints_have_explicit_contracts():
    schema = app.openapi()
    paths = schema["paths"]

    legacy_schema = paths["/api/v1/institutions"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    flat_schema = paths["/api/v1/institutions/flat"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    hierarchy_schema = paths["/api/v1/institutions/hierarchy"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert legacy_schema["anyOf"] == [
        {"$ref": "#/components/schemas/InstitutionListResponse"},
        {"$ref": "#/components/schemas/InstitutionHierarchyResponse"},
    ]
    assert flat_schema == {"$ref": "#/components/schemas/InstitutionListResponse"}
    assert hierarchy_schema == {"$ref": "#/components/schemas/InstitutionHierarchyResponse"}


def test_openapi_institution_helper_routes_are_typed():
    schema = app.openapi()
    paths = schema["paths"]

    taxonomy_schema = paths["/api/v1/institutions/taxonomy"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    aminer_schema = paths["/api/v1/institutions/aminer/search-org"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    reports_generate = paths["/api/v1/reports/generate"]["post"]["responses"]

    assert taxonomy_schema == {"$ref": "#/components/schemas/InstitutionTaxonomyResponse"}
    assert aminer_schema == {"$ref": "#/components/schemas/AminerOrganizationSearchResponse"}
    assert "400" in reports_generate
    assert "501" in reports_generate


@pytest.mark.asyncio
async def test_generate_report_unknown_dimension_returns_400():
    request = ReportGenerateRequest(dimension="unknown")

    with pytest.raises(HTTPException) as exc:
        await reports.generate_report(request)

    assert exc.value.status_code == 400
    assert "Unknown dimension" in exc.value.detail


@pytest.mark.asyncio
async def test_generate_report_planned_dimension_returns_501():
    request = ReportGenerateRequest(dimension="policy")

    with pytest.raises(HTTPException) as exc:
        await reports.generate_report(request)

    assert exc.value.status_code == 501
    assert "not implemented" in exc.value.detail


def _raise_intel_data_error(*_args, **_kwargs):
    raise IntelDataLoadError("policy_intel", "feed.json", "missing")


def test_policy_route_wraps_missing_processed_data_as_503():
    with pytest.raises(HTTPException) as exc:
        policy_api._call_policy_service(_raise_intel_data_error)

    assert exc.value.status_code == 503
    assert "Run the intel pipeline first" in exc.value.detail


def test_personnel_route_wraps_missing_processed_data_as_503():
    with pytest.raises(HTTPException) as exc:
        personnel_api._call_personnel_service(_raise_intel_data_error)

    assert exc.value.status_code == 503
    assert "Run the intel pipeline first" in exc.value.detail


def test_tech_frontier_route_wraps_missing_processed_data_as_503():
    with pytest.raises(HTTPException) as exc:
        tech_frontier_api._call_tf_service(_raise_intel_data_error)

    assert exc.value.status_code == 503
    assert "Run the intel pipeline first" in exc.value.detail
