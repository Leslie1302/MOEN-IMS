def generate_abbreviation(name, max_length=5):
    """
    Generate abbreviation from name.
    Uses first letters of each word for multi-word names,
    or truncates single words.
    
    Examples:
        "Accra Metropolitan" -> "AM"
        "Greater Accra" -> "GA"
        "Osu" -> "OSU"
    """
    if not name:
        return ""
    words = name.strip().upper().split()
    if len(words) > 1:
        # Use first letter of each word
        abbr = ''.join(w[0] for w in words if w)
        return abbr[:max_length]
    # Single word - use first characters
    return name[:max_length].upper()
