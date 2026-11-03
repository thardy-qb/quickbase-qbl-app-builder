_NAMED_COLUMN_TYPES = tuple(
    f"QB::ConnectedColumn::{name}" for name in (
        "BigInt", "Decimal", "Text", "TimestampWithTimeZone",
        "SmallInt", "TinyInt", "Integer", "Serial", "Float", "Double",
        "Char", "Varchar",
        "Date", "Time", "Timestamp", "Interval", "TimeWithTimeZone",
        "Binary", "Blob", "VarBinary",
        "Boolean", "XML", "UserDefinedType",
    )
)

_SOURCE_TYPES = ()

_SOURCE_TYPES = (
    "QB::ConnectedDataSource::AdminConsole",
    "QB::ConnectedDataSource::Sample",
)


CONNECTED_TABLE_SCHEMA = {
    column_type: {"required": ["Name"], "optional": []}
    for column_type in _NAMED_COLUMN_TYPES
}

CONNECTED_TABLE_SCHEMA.update({
    "QB::ConnectedColumn::Placeholder": {
        "required": [],
        "optional": ["Type", "Name"],
    },

    **{
        source: {"required": [], "optional": ["Owner", "ConnectionId", "IsPlaceholder"]}
        for source in _SOURCE_TYPES
    },

    "QB::ConnectedDataSource::Quickbase": {
        "required": ["ConnectionId"],
        "optional": ["Owner", "IsPlaceholder"],
    },

    "QB::ConnectedRecordSet": {
        "required": [],
        "optional": ["SetType", "ExternalSetIsInSolution", "ExternalSetId",
                     "Name", "PrimaryKey"],
    },

    "QB::PlaceholderRecordSet": {
        "required": [],
        "optional": ["SetType", "ExternalSetId"],
    },
})
