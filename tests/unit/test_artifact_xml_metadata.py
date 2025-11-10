"""
Test that artifact XML serialization includes full metadata.

Tests the fix for missing metadata in artifact context (rows, columns, schema, preview).
"""

import pytest
from uuid import uuid4
from datetime import datetime, UTC

from roma_dspy.types import Artifact, ArtifactMetadata, ArtifactReference, ArtifactType, MediaType


def test_artifact_reference_includes_metadata_in_xml():
    """Test that ArtifactReference.to_xml_element() includes full metadata."""
    # Create artifact with rich metadata
    metadata = ArtifactMetadata(
        description="Full order book depth for BTC/USDT from Binance",
        mime_type="application/x-parquet",
        size_bytes=38141,
        row_count=10000,
        column_count=3,
        data_schema={
            "price": "double",
            "quantity": "double",
            "side": "string",
        },
        preview="price,quantity,side\n65432.10,0.5,bid\n65432.20,0.3,ask",
        usage_hints=[
            "Use this order book to analyze market depth",
            "Contains 5000 bid and 5000 ask levels",
        ],
    )

    artifact = Artifact(
        artifact_id=uuid4(),
        name="BTCUSDT_Binance_OrderBook_Depth",
        artifact_type=ArtifactType.DATA_FETCH,
        media_type=MediaType.FILE,
        storage_path="/opt/sentient/executions/test/artifacts/binance/order_books/BTCUSDT_book.parquet",
        created_by_task="test-task-123",
        created_by_module="BinanceToolkit",
        created_at=datetime.now(UTC),
        metadata=metadata,
    )

    # Create reference from artifact
    ref = ArtifactReference.from_artifact(artifact)

    # Generate XML
    xml = ref.to_xml_element()

    # Verify all metadata is present in XML
    assert "<description>" in xml
    assert "Full order book depth for BTC/USDT from Binance" in xml

    # Metadata section
    assert "<metadata>" in xml
    assert "</metadata>" in xml

    # MIME type
    assert "<mime_type>application/x-parquet</mime_type>" in xml

    # Size info
    assert "<size_bytes>38141</size_bytes>" in xml
    assert "<size_kb>37.25</size_kb>" in xml

    # Structure info
    assert "<row_count>10000</row_count>" in xml
    assert "<column_count>3</column_count>" in xml

    # Schema
    assert "<schema>" in xml
    assert 'name="price" type="double"' in xml
    assert 'name="quantity" type="double"' in xml
    assert 'name="side" type="string"' in xml

    # Preview
    assert "<preview>" in xml
    assert "price,quantity,side" in xml

    # Usage hints
    assert "<usage_hints>" in xml
    assert "<hint>Use this order book to analyze market depth</hint>" in xml
    assert "<hint>Contains 5000 bid and 5000 ask levels</hint>" in xml


def test_artifact_reference_handles_minimal_metadata():
    """Test that XML works with minimal metadata (no schema, preview, etc.)."""
    metadata = ArtifactMetadata(
        description="Simple artifact with minimal metadata",
    )

    artifact = Artifact(
        artifact_id=uuid4(),
        name="simple_artifact",
        artifact_type=ArtifactType.DATA_PROCESSED,
        media_type=MediaType.FILE,
        storage_path="/tmp/simple.parquet",
        created_by_task="task-456",
        created_by_module="TestModule",
        created_at=datetime.now(UTC),
        metadata=metadata,
    )

    ref = ArtifactReference.from_artifact(artifact)
    xml = ref.to_xml_element()

    # Should have description
    assert "<description>" in xml
    assert "Simple artifact with minimal metadata" in xml

    # Should not have metadata section if no fields are present
    # (metadata section is only added if there are metadata_parts)
    assert "<metadata>" not in xml or xml.count("<metadata>") == xml.count("</metadata>")


def test_artifact_reference_escapes_xml_special_characters():
    """Test that XML special characters are properly escaped."""
    metadata = ArtifactMetadata(
        description='Artifact with <special> & "characters"',
        preview='Data with <tags> & "quotes" and \'apostrophes\'',
        data_schema={
            "col<1>": "string",
            'col"2"': "int64",
        },
    )

    artifact = Artifact(
        artifact_id=uuid4(),
        name="special_chars_artifact",
        artifact_type=ArtifactType.DATA_PROCESSED,
        media_type=MediaType.FILE,
        storage_path="/tmp/special.parquet",
        created_by_task="task-789",
        created_by_module="TestModule",
        created_at=datetime.now(UTC),
        metadata=metadata,
    )

    ref = ArtifactReference.from_artifact(artifact)
    xml = ref.to_xml_element()

    # Verify escaping in description
    assert "&lt;special&gt;" in xml
    assert "&amp;" in xml
    assert "&quot;" in xml

    # Verify escaping in preview
    assert "Data with &lt;tags&gt;" in xml

    # Verify escaping in schema
    assert "col&lt;1&gt;" in xml
    assert 'col&quot;2&quot;' in xml


def test_artifact_reference_with_relevance_score():
    """Test that relevance score is included in XML when present."""
    metadata = ArtifactMetadata(
        description="Relevant artifact",
    )

    artifact = Artifact(
        artifact_id=uuid4(),
        name="relevant_artifact",
        artifact_type=ArtifactType.DATA_FETCH,
        media_type=MediaType.FILE,
        storage_path="/tmp/relevant.parquet",
        created_by_task="task-999",
        created_by_module="TestModule",
        created_at=datetime.now(UTC),
        metadata=metadata,
    )

    # Create reference with relevance score
    ref = ArtifactReference.from_artifact(artifact, relevance_score=0.85)
    xml = ref.to_xml_element()

    # Verify relevance score in XML
    assert 'relevance="0.85"' in xml
