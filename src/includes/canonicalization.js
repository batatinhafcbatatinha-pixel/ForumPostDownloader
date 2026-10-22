const canonicalizeThreadTitle = title => {
    const normalized = String(title || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    const lower = normalized.toLowerCase();
    return normalized
        .replace(/\s+@[a-z0-9_.-]+$/i, '')
        .replace(/\s*\([^)]*\)\s*$/g, '')
        .replace(/\s*\[[^\]]*\]\s*$/g, '')
        .trim() || lower;
};