"""Source-span checks independent of the AI provider."""

def grounded(span: dict, sources: dict[str, str]) -> bool:
    """A span is {source_id,start,end,text}; offsets are Python character offsets."""
    if not isinstance(span, dict) or not isinstance(sources, dict):
        return False
    source_id = span.get("source_id")
    if not isinstance(source_id, str):
        return False
    source = sources.get(source_id)
    start, end, claimed = span.get("start"), span.get("end"), span.get("text")
    return (isinstance(source, str) and type(start) is int and type(end) is int
            and 0 <= start < end <= len(source) and isinstance(claimed, str)
            and source[start:end] == claimed)
