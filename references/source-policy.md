# Source and evidence policy

Crossref is the default metadata source. Query bounded publication dates and journal bibliographic terms. Treat returned records as candidates and enforce canonical journal matching locally.

Normalize DOI, title, journal, author, date, URL, and abstract. Strip markup from abstracts. Deduplicate by lowercase DOI; without DOI, use normalized title plus journal and publication year.

Topic classification is multi-label. A topic term must match title or abstract. If a term is generic (`machine learning`, `optimisation`, `spatial analysis`), also require a configured domain-context term. Store matched terms as inclusion evidence.

Summaries must use title and abstract only. If the abstract is absent, label the item “Metadata-only; contribution could not be summarized from the available record.” Never infer results from the title alone.
