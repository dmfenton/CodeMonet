"""Tests for the public gallery API endpoints."""

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Test UUID for user with public gallery
TEST_USER_ID = "12345678-1234-1234-1234-123456789abc"
TEST_USER_ID_PRIVATE = "87654321-4321-4321-4321-cba987654321"


class TestPublicGalleryStrokes:
    """Tests for GET /public/gallery/{user_id}/{piece_id}/strokes endpoint."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create user gallery structure with UUID-based directory
            user_dir = Path(tmpdir) / TEST_USER_ID / "gallery"
            user_dir.mkdir(parents=True)

            # Create a test piece
            piece_data = {
                "strokes": [{"type": "line", "points": [[0, 0], [100, 100]]}],
                "piece_number": 1,
                "created_at": "2026-01-01T00:00:00Z",
            }
            (user_dir / "piece_0001.json").write_text(json.dumps(piece_data))

            yield tmpdir

    @pytest.fixture
    def mock_public_user(self):
        """Create a mock user with public gallery."""
        user = MagicMock()
        user.id = TEST_USER_ID
        user.gallery_public = True
        return user

    @pytest.fixture
    def mock_private_user(self):
        """Create a mock user with private gallery."""
        user = MagicMock()
        user.id = TEST_USER_ID_PRIVATE
        user.gallery_public = False
        return user

    @pytest.fixture
    def client(self, temp_workspace, mock_public_user):
        """Create test client with mocked workspace and repository."""
        with (
            patch("code_monet.routes.public_gallery.settings") as mock_settings,
            patch("code_monet.routes.public_gallery.repository") as mock_repo,
            patch("code_monet.routes.public_gallery.get_session") as mock_get_session,
        ):
            mock_settings.workspace_base_dir = temp_workspace

            # Mock repository.get_user_by_id
            async def get_user_by_id(_session, user_id):
                if user_id == TEST_USER_ID:
                    return mock_public_user
                return None

            mock_repo.get_user_by_id = AsyncMock(side_effect=get_user_by_id)

            # Mock get_session context manager
            mock_session = MagicMock()
            mock_context = MagicMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_context

            from code_monet.main import app

            yield TestClient(app)

    def test_valid_request_returns_strokes(self, client):
        """Test valid user_id and piece_id returns stroke data."""
        response = client.get(f"/public/gallery/{TEST_USER_ID}/piece_0001/strokes")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "piece_0001"
        assert len(data["strokes"]) == 1
        assert data["piece_number"] == 1

    def test_invalid_user_id_not_uuid(self, client):
        """Test non-UUID user_id is rejected."""
        response = client.get("/public/gallery/abc/piece_0001/strokes")

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid user_id"

    def test_invalid_user_id_numeric(self, client):
        """Test numeric user_id is rejected (must be UUID)."""
        response = client.get("/public/gallery/123/piece_0001/strokes")

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid user_id"

    def test_invalid_user_id_path_traversal_dots(self, client):
        """Test path traversal with .. in user_id is rejected."""
        response = client.get("/public/gallery/../etc/piece_0001/strokes")

        # Either 400 (validation) or 404 (route not found) blocks the attack
        assert response.status_code in (400, 404)

    def test_invalid_user_id_path_traversal_encoded(self, client):
        """Test path traversal with encoded dots is rejected."""
        # %2e%2e is URL-encoded ..
        response = client.get("/public/gallery/%2e%2e/piece_0001/strokes")

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid user_id"

    def test_invalid_piece_id_path_traversal(self, client):
        """Test path traversal in piece_id is rejected."""
        response = client.get(f"/public/gallery/{TEST_USER_ID}/../../../etc/passwd/strokes")

        # Either 400 (validation) or 404 (route not found) blocks the attack
        assert response.status_code in (400, 404)

    def test_invalid_piece_id_special_chars(self, client):
        """Test piece_id with special characters is rejected."""
        response = client.get(f"/public/gallery/{TEST_USER_ID}/piece..0001/strokes")

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid piece_id"

    def test_invalid_piece_id_slash(self, client):
        """Test piece_id with slash is rejected."""
        response = client.get(f"/public/gallery/{TEST_USER_ID}/piece/0001/strokes")

        # FastAPI will treat this as a different route, resulting in 404
        assert response.status_code == 404

    def test_valid_piece_id_with_underscore(self, client):
        """Test piece_id with underscore is allowed."""
        response = client.get(f"/public/gallery/{TEST_USER_ID}/piece_0001/strokes")

        assert response.status_code == 200

    def test_valid_piece_id_with_hyphen(self, client, temp_workspace):
        """Test piece_id with hyphen is allowed."""
        # Create a piece with hyphen in name
        user_dir = Path(temp_workspace) / TEST_USER_ID / "gallery"
        piece_data = {"strokes": [], "piece_number": 2}
        (user_dir / "piece-0002.json").write_text(json.dumps(piece_data))

        response = client.get(f"/public/gallery/{TEST_USER_ID}/piece-0002/strokes")

        assert response.status_code == 200

    def test_nonexistent_user_returns_404(self, client):
        """Test request for nonexistent user returns 404."""
        nonexistent_uuid = "99999999-9999-9999-9999-999999999999"
        response = client.get(f"/public/gallery/{nonexistent_uuid}/piece_0001/strokes")

        assert response.status_code == 404
        assert response.json()["detail"] == "Gallery not found"

    def test_nonexistent_piece_returns_404(self, client):
        """Test request for nonexistent piece returns 404."""
        response = client.get(f"/public/gallery/{TEST_USER_ID}/nonexistent/strokes")

        assert response.status_code == 404
        assert response.json()["detail"] == "Piece not found"

    def test_empty_user_id_rejected(self, client):
        """Test empty user_id is handled by FastAPI routing."""
        response = client.get("/public/gallery//piece_0001/strokes")

        # FastAPI treats this as a different route
        assert response.status_code in (404, 307)  # Not found or redirect

    def test_private_gallery_returns_404(self, temp_workspace, mock_private_user):
        """Test that private gallery is not accessible."""
        with (
            patch("code_monet.routes.public_gallery.settings") as mock_settings,
            patch("code_monet.routes.public_gallery.repository") as mock_repo,
            patch("code_monet.routes.public_gallery.get_session") as mock_get_session,
        ):
            mock_settings.workspace_base_dir = temp_workspace

            # Mock repository.get_user_by_id to return private user
            async def get_user_by_id(_session, user_id):
                if user_id == TEST_USER_ID_PRIVATE:
                    return mock_private_user
                return None

            mock_repo.get_user_by_id = AsyncMock(side_effect=get_user_by_id)

            # Mock get_session context manager
            mock_session = MagicMock()
            mock_context = MagicMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_context

            from code_monet.main import app

            client = TestClient(app)
            response = client.get(f"/public/gallery/{TEST_USER_ID_PRIVATE}/piece_0001/strokes")

            assert response.status_code == 404
            assert response.json()["detail"] == "Gallery not found"

    def test_uppercase_uuid_passes_validation(self, client):
        """Test uppercase UUID passes validation but returns 404 (case-sensitive lookup)."""
        response = client.get(f"/public/gallery/{TEST_USER_ID.upper()}/piece_0001/strokes")
        # UUID regex is case-insensitive so it passes validation,
        # but DB lookup is case-sensitive so user won't be found
        assert response.status_code == 404
        assert response.json()["detail"] == "Gallery not found"


class TestPublicGalleryThumbnail:
    """GET /public/gallery/{user_id}/{piece_id}/thumbnail.png against a real workspace."""

    @pytest.fixture
    def workspace(self, tmp_path, monkeypatch):
        from code_monet.config import settings

        monkeypatch.setattr(settings, "workspace_base_dir", str(tmp_path))
        gallery = tmp_path / TEST_USER_ID / "gallery"
        gallery.mkdir(parents=True)
        line = {"type": "line", "points": [{"x": 0, "y": 0}, {"x": 1600, "y": 1200}]}
        for name, number in (("piece_000012.json", 12), ("piece_003.json", 3)):
            (gallery / name).write_text(
                json.dumps(
                    {"piece_number": number, "strokes": [line], "width": 1600, "height": 1200}
                )
            )
        return gallery

    @pytest.fixture
    def db(self):
        public_user = MagicMock(id=TEST_USER_ID, gallery_public=True)
        private_user = MagicMock(id=TEST_USER_ID_PRIVATE, gallery_public=False)
        users = {TEST_USER_ID: public_user, TEST_USER_ID_PRIVATE: private_user}
        with (
            patch("code_monet.routes.public_gallery.repository") as mock_repo,
            patch("code_monet.routes.public_gallery.get_session") as mock_get_session,
        ):
            mock_repo.get_user_by_id = AsyncMock(side_effect=lambda _s, uid: users.get(uid))
            mock_context = MagicMock()
            mock_context.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_context
            yield mock_repo

    @pytest.fixture
    def client(self, db):  # noqa: ARG002 - db patches must be active for requests
        from code_monet.main import app

        return TestClient(app)

    def _url(self, user_id: str, piece_id: str) -> str:
        return f"/public/gallery/{user_id}/{piece_id}/thumbnail.png"

    def test_renders_small_thumbnail_once_then_serves_persisted_file(
        self, client, workspace
    ) -> None:
        from PIL import Image

        first = client.get(self._url(TEST_USER_ID, "piece_000012"))
        assert first.status_code == 200
        assert first.headers["content-type"] == "image/png"
        assert "max-age=604800" in first.headers["cache-control"]
        assert Image.open(io.BytesIO(first.content)).size == (640, 480)
        thumbnail = workspace / "piece_000012.thumb.png"
        assert thumbnail.read_bytes() == first.content

        with patch("code_monet.workspace.gallery.render_strokes_async") as render:
            second = client.get(self._url(TEST_USER_ID, "piece_000012"))
        render.assert_not_called()
        assert second.content == first.content

    def test_does_not_load_workspace_state(self, client, workspace) -> None:
        with patch("code_monet.workspace.WorkspaceState.load_for_user") as load:
            response = client.get(self._url(TEST_USER_ID, "piece_000012"))
        assert response.status_code == 200
        load.assert_not_called()
        assert not (workspace.parent / "workspace.json").exists()

    @pytest.mark.usefixtures("workspace")
    def test_serves_legacy_three_digit_piece(self, client) -> None:
        response = client.get(self._url(TEST_USER_ID, "piece_000003"))
        assert response.status_code == 200

    @pytest.mark.usefixtures("workspace")
    def test_private_gallery_is_not_found(self, client) -> None:
        response = client.get(self._url(TEST_USER_ID_PRIVATE, "piece_000012"))
        assert response.status_code == 404

    @pytest.mark.usefixtures("workspace")
    def test_missing_piece_is_not_found(self, client) -> None:
        response = client.get(self._url(TEST_USER_ID, "piece_000099"))
        assert response.status_code == 404

    @pytest.mark.parametrize("piece_id", ["piece_abc", "piece_1x", "piece_", "thumb_1"])
    def test_rejects_malformed_piece_id(self, client, db, piece_id) -> None:
        response = client.get(self._url(TEST_USER_ID, piece_id))
        assert response.status_code == 400
        db.get_user_by_id.assert_not_called()

    def test_rejects_invalid_user_id(self, client, db) -> None:
        response = client.get(self._url("not-a-uuid", "piece_000012"))
        assert response.status_code == 400
        db.get_user_by_id.assert_not_called()
