import time
from typing import cast
from cache import CacheError, cache_get, cache_set, normalize_tags
import osmnx as ox
from networkx import MultiDiGraph
from geopandas import GeoDataFrame


def fetch_graph(point, dist) -> MultiDiGraph | None:
    """
    Fetch street network graph from OpenStreetMap.

    Uses caching to avoid redundant downloads. Fetches all network types
    within the specified distance from the center point.

    Args:
        point: (latitude, longitude) tuple for center point
        dist: Distance in meters from center point

    Returns:
        MultiDiGraph of street network, or None if fetch fails
    """
    lat, lon = point
    graph = f"graph_{lat}_{lon}_{dist}"
    cached = cache_get(graph)
    if cached is not None:
        print("✓ Using cached street network")
        return cast(MultiDiGraph, cached)

    try:
        g = ox.graph_from_point(point, dist=dist, dist_type='bbox', network_type='all', truncate_by_edge=True)
        # Rate limit between requests
        time.sleep(0.5)
        try:
            cache_set(graph, g)
        except CacheError as e:
            print(e)
        return g
    except Exception as e:
        print(f"OSMnx error while fetching graph: {e}")
        return None


def fetch_features(point, dist, tags, name) -> GeoDataFrame | None:
    """
    Fetch geographic features (water, parks, etc.) from OpenStreetMap.

    Uses caching to avoid redundant downloads. Fetches features matching
    the specified OSM tags within distance from center point.

    Args:
        point: (latitude, longitude) tuple for center point
        dist: Distance in meters from center point
        tags: Dictionary of OSM tags to filter features
        name: Name for this feature type (for caching and logging)

    Returns:
        GeoDataFrame of features, or None if fetch fails
    """
    lat, lon = point

    tag_str = normalize_tags(tags)
    features = f"{name}_{lat}_{lon}_{dist}_{tag_str}"
    cached = cache_get(features)
    if cached is not None:
        print(f"✓ Using cached {name}")
        return cast(GeoDataFrame, cached)

    try:
        data = ox.features_from_point(
            point,
            dist=dist,
            tags=tags
        )

        time.sleep(0.3)
        try:
            cache_set(features, data)
        except CacheError as e:
            print(e)
        return data
    except Exception as e:
        print(f"OSMnx error while fetching features: {e}")
        return None