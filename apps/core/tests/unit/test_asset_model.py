from core.db.models.asset import AssetType, UploadedAsset


def test_asset_type_has_document() -> None:
    assert AssetType.DOCUMENT == "document"


def test_uploaded_asset_has_folder_id() -> None:
    columns = {c.key for c in UploadedAsset.__table__.columns}
    assert "folder_id" in columns
