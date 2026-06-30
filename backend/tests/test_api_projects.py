"""Integration tests for the /api/v1/projects REST API."""
import pytest
from httpx import AsyncClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestProjectsAPI:
    # ── List ──────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, client: AsyncClient):
        r = await client.get("/api/v1/projects")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_projects_after_create(self, client: AsyncClient):
        await client.post("/api/v1/projects", json={"name": "Listed Project"})
        r = await client.get("/api/v1/projects")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Listed Project"

    @pytest.mark.asyncio
    async def test_list_projects_pagination_fields(self, client: AsyncClient):
        r = await client.get("/api/v1/projects?page=1&page_size=10")
        assert r.status_code == 200
        data = r.json()
        assert "page" in data
        assert "page_size" in data
        assert "has_next" in data
        assert "has_prev" in data

    # ── Create ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_project(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "My Test Project"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Test Project"
        assert data["status"] == "created"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_project_with_description(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/projects",
            json={"name": "With Desc", "description": "A test project description"},
        )
        assert r.status_code == 201
        assert r.json()["description"] == "A test project description"

    @pytest.mark.asyncio
    async def test_create_project_missing_name_fails(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_empty_name_fails(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": ""})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_returns_id(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "ID Test"})
        assert r.status_code == 201
        assert "id" in r.json()
        assert len(r.json()["id"]) > 0

    @pytest.mark.asyncio
    async def test_create_project_has_timestamps(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Timestamp Test"})
        data = r.json()
        assert "created_at" in data
        assert "updated_at" in data

    # ── Get single ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_project(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Fetch Me"})
        project_id = r.json()["id"]

        r = await client.get(f"/api/v1/projects/{project_id}")
        assert r.status_code == 200
        assert r.json()["id"] == project_id

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client: AsyncClient):
        r = await client.get("/api/v1/projects/nonexistent-id-abc-123")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_has_input_files_status(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Files Test"})
        pid = r.json()["id"]
        r = await client.get(f"/api/v1/projects/{pid}")
        data = r.json()
        assert "input_files_status" in data

    # ── Update ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_project_name(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Original"})
        pid = r.json()["id"]

        r = await client.patch(f"/api/v1/projects/{pid}", json={"name": "Updated"})
        assert r.status_code == 200
        assert r.json()["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_project_description(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Desc Project"})
        pid = r.json()["id"]

        r = await client.patch(
            f"/api/v1/projects/{pid}", json={"description": "New description"}
        )
        assert r.status_code == 200
        assert r.json()["description"] == "New description"

    @pytest.mark.asyncio
    async def test_update_project_not_found(self, client: AsyncClient):
        r = await client.patch(
            "/api/v1/projects/nonexistent-id", json={"name": "Updated"}
        )
        assert r.status_code == 404

    # ── Delete ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_project(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Delete Me"})
        pid = r.json()["id"]

        r = await client.delete(f"/api/v1/projects/{pid}")
        assert r.status_code == 200

        r = await client.get(f"/api/v1/projects/{pid}")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project_returns_message(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Del Msg"})
        pid = r.json()["id"]
        r = await client.delete(f"/api/v1/projects/{pid}")
        data = r.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, client: AsyncClient):
        r = await client.delete("/api/v1/projects/nonexistent-id")
        assert r.status_code == 404

    # ── Archive ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_archive_project(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Archive Me"})
        pid = r.json()["id"]

        r = await client.post(f"/api/v1/projects/{pid}/archive")
        assert r.status_code == 200
        assert r.json()["status"] == "archived"

    @pytest.mark.asyncio
    async def test_archive_project_not_found(self, client: AsyncClient):
        r = await client.post("/api/v1/projects/nonexistent-id/archive")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_archived_projects_excluded_from_list_by_default(
        self, client: AsyncClient
    ):
        r = await client.post("/api/v1/projects", json={"name": "To Archive"})
        pid = r.json()["id"]
        await client.post(f"/api/v1/projects/{pid}/archive")

        r = await client.get("/api/v1/projects")
        items = r.json()["items"]
        assert all(p["id"] != pid for p in items)

    # ── File upload ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upload_file_wrong_type(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Upload Test"})
        pid = r.json()["id"]

        # Uploading a .exe as a script should fail validation
        files = {"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")}
        r = await client.post(f"/api/v1/projects/{pid}/files/script", files=files)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_script_txt(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Script Upload"})
        pid = r.json()["id"]

        files = {"file": ("script.txt", b"This is the script content.", "text/plain")}
        r = await client.post(f"/api/v1/projects/{pid}/files/script", files=files)
        assert r.status_code == 200
        data = r.json()
        assert data["file_type"] == "script"
        assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_upload_scenes_json(self, client: AsyncClient):
        import json as json_mod
        r = await client.post("/api/v1/projects", json={"name": "Scenes Upload"})
        pid = r.json()["id"]

        scenes = {"scenes": [{"scene_id": 1, "narration": "hi", "duration": 5}]}
        files = {
            "file": (
                "scenes.json",
                json_mod.dumps(scenes).encode(),
                "application/json",
            )
        }
        r = await client.post(f"/api/v1/projects/{pid}/files/scenes", files=files)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_file_project_not_found(self, client: AsyncClient):
        files = {"file": ("script.txt", b"content", "text/plain")}
        r = await client.post(
            "/api/v1/projects/nonexistent/files/script", files=files
        )
        assert r.status_code == 404

    # ── Validate ──────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_validate_endpoint_missing_files(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Validate Test"})
        pid = r.json()["id"]
        r = await client.post(f"/api/v1/projects/{pid}/validate")
        assert r.status_code == 200
        data = r.json()
        assert data["all_valid"] is False

    @pytest.mark.asyncio
    async def test_validate_endpoint_returns_results_dict(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Val Results"})
        pid = r.json()["id"]
        r = await client.post(f"/api/v1/projects/{pid}/validate")
        data = r.json()
        assert "results" in data
        assert "scenes" in data["results"]
        assert "seo" in data["results"]

    @pytest.mark.asyncio
    async def test_validate_endpoint_not_found(self, client: AsyncClient):
        r = await client.post("/api/v1/projects/nonexistent-id/validate")
        assert r.status_code == 404

    # ── Duplicate ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_duplicate_project(self, client: AsyncClient):
        r = await client.post("/api/v1/projects", json={"name": "Original For Copy"})
        pid = r.json()["id"]

        r = await client.post(f"/api/v1/projects/{pid}/duplicate")
        assert r.status_code == 201
        dup = r.json()
        assert dup["id"] != pid
        assert "copy" in dup["name"].lower()

    @pytest.mark.asyncio
    async def test_duplicate_project_not_found(self, client: AsyncClient):
        r = await client.post("/api/v1/projects/nonexistent/duplicate")
        assert r.status_code == 404
