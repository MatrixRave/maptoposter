#!/usr/bin/env python3
"""
City Map Poster Generator

This module generates beautiful, minimalist map posters for any city in the world.
It fetches OpenStreetMap data using OSMnx, applies customizable themes, and creates
high-quality poster-ready images with roads, water features, and parks.
"""

import argparse
import sys
import matplotlib.pyplot as plt
from fetch_data import fetch_features, fetch_graph
import osmnx as ox
from lat_lon_parser import parse
from matplotlib.font_manager import FontProperties
from tqdm import tqdm
from font_management import load_fonts
from poster_text import is_latin_script
from poster_util import create_gradient_fade, generate_output_filename, get_coordinates, get_crop_limits, get_edge_colors_by_type, get_edge_widths_by_type
from themes import get_available_themes, list_themes, load_theme

FONTS_DIR = "fonts"
FONTS = load_fonts()

# Font loading now handled by font_management.py module

def create_poster(
    city,
    country,
    point,
    dist,
    output_file,
    output_format,
    text_options,
    width=12,
    height=16,
    country_label=None,
    name_label=None,
    display_city=None,
    display_country=None,
    fonts=None,
):
    """
    Generate a complete map poster with roads, railways, water, parks, and typography.
    Maintains aspect ratio, correct sizes, and text visibility.
    """
    # Display names
    display_city = display_city or name_label or city
    display_country = display_country or country_label or country

    print(f"\nGenerating map for {city}, {country}...")

    with tqdm(total=4, desc="Fetching map data", unit="step", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
        compensated_dist = dist * (max(height, width) / min(height, width)) / 4

        # Streets
        pbar.set_description("Downloading street network")
        g = fetch_graph(point, compensated_dist)
        if g is None:
            raise RuntimeError("Failed to retrieve street network data.")
        pbar.update(1)

        # Water
        pbar.set_description("Downloading water features")
        water = fetch_features(
            point, compensated_dist,
            tags={"natural": ["water", "bay", "strait"], "waterway": "riverbank"},
            name="water",
        )
        pbar.update(1)

        # Parks
        pbar.set_description("Downloading parks/green spaces")
        parks = fetch_features(
            point, compensated_dist,
            tags={"leisure": "park", "landuse": "grass"},
            name="parks",
        )
        pbar.update(1)

        # Railways
        pbar.set_description("Downloading railways")
        railways = fetch_features(
            point, compensated_dist,
            tags={"railway": ["rail", "subway", "tram", "light_rail",
                              "narrow_gauge", "monorail",
                              "service", "yard", "siding"]},
            name="railways",
        )
        pbar.update(1)
    print("✓ All data retrieved successfully!")

    fig, ax = plt.subplots(figsize=(width, height), facecolor=THEME["bg"])
    ax.set_facecolor(THEME["bg"])
    ax.set_position((0.0, 0.0, 1.0, 1.0))

    # Project streets graph
    g_proj = ox.project_graph(g)

    # Compute cropping limits once
    crop_xlim, crop_ylim = get_crop_limits(g_proj, point, fig, compensated_dist)

    # ----------------------------
    # 3. Plot layers
    # ----------------------------
    # Water
    if water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not water_polys.empty:
            try:
                water_polys = ox.projection.project_gdf(water_polys)
            except Exception:
                water_polys = water_polys.to_crs(g_proj.graph["crs"])
            water_polys.plot(ax=ax, facecolor=THEME["water"], edgecolor="none", zorder=0.5)

    if parks is not None and not parks.empty:
        parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not parks_polys.empty:
            try:
                parks_polys = ox.projection.project_gdf(parks_polys)
            except Exception:
                parks_polys = parks_polys.to_crs(g_proj.graph["crs"])
            parks_polys.plot(ax=ax, facecolor=THEME["parks"], edgecolor="none", zorder=0.8)

    print("Applying road hierarchy colors...")
    edge_colors = get_edge_colors_by_type(g_proj)
    edge_widths = get_edge_widths_by_type(g_proj)

    ox.plot_graph(
        g_proj,
        ax=ax,
        bgcolor=THEME["bg"],
        node_size=0,
        edge_color=edge_colors,
        edge_linewidth=edge_widths,
        show=False,
        close=False,
    )

    if railways is not None and not railways.empty:
        rail_lines = railways[railways.geometry.type.isin(["LineString", "MultiLineString"])]
        if not rail_lines.empty:
            try:
                rail_lines = ox.projection.project_gdf(rail_lines)
            except Exception:
                rail_lines = rail_lines.to_crs(g_proj.graph["crs"])
            for railway_type, group in rail_lines.groupby("railway"):
                if railway_type in ["rail", "subway"]:
                    color = THEME.get("rail_heavy")
                    width = 1.0
                elif railway_type in ["light_rail", "tram"]:
                    color = THEME.get("rail_light")
                    width = 0.7
                elif railway_type in ["narrow_gauge", "funicular", "monorail"]:
                    color = THEME.get("rail_special")
                    width = 0.6
                elif railway_type in ["service", "yard", "siding"]:
                    color = THEME.get("rail_service")
                    width = 0.4
                else:
                    color = THEME.get("rail_default")
                    width = 0.5
                group.plot(ax=ax, color=color, edgecolor="none", zorder=1)

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(crop_xlim)
    ax.set_ylim(crop_ylim)

    # Gradients
    create_gradient_fade(ax, THEME["gradient_color"], location="bottom", zorder=10)
    create_gradient_fade(ax, THEME["gradient_color"], location="top", zorder=10)

   # Calculate scale factor based on smaller dimension (reference 12 inches)
    # This ensures text scales properly for both portrait and landscape orientations
    scale_factor = min(height, width) / 12.0

    # Base font sizes (at 12 inches width)
    base_main = 60
    base_sub = 22
    base_coords = 14
    base_attr = 8

    # 4. Typography - use custom fonts if provided, otherwise use default FONTS
    active_fonts = fonts or FONTS
    if active_fonts:
        # font_main is calculated dynamically later based on length
        font_sub = FontProperties(
            fname=active_fonts["light"], size=base_sub * scale_factor
        )
        font_coords = FontProperties(
            fname=active_fonts["regular"], size=base_coords * scale_factor
        )
        font_attr = FontProperties(
            fname=active_fonts["light"], size=base_attr * scale_factor
        )
    else:
        # Fallback to system fonts
        font_sub = FontProperties(
            family="monospace", weight="normal", size=base_sub * scale_factor
        )
        font_coords = FontProperties(
            family="monospace", size=base_coords * scale_factor
        )
        font_attr = FontProperties(family="monospace", size=base_attr * scale_factor)

    # Format city name based on script type
    # Latin scripts: apply uppercase and letter spacing for aesthetic
    # Non-Latin scripts (CJK, Thai, Arabic, etc.): no spacing, preserve case structure
    if is_latin_script(display_city):
        # Latin script: uppercase with letter spacing (e.g., "P  A  R  I  S")
        spaced_city = "  ".join(list(display_city.upper()))
    else:
        # Non-Latin script: no spacing, no forced uppercase
        # For scripts like Arabic, Thai, Japanese, etc.
        spaced_city = display_city

    # Dynamically adjust font size based on city name length to prevent truncation
    # We use the already scaled "main" font size as the starting point.
    base_adjusted_main = base_main * scale_factor
    city_char_count = len(display_city)

    # Heuristic: If length is > 10, start reducing.
    if city_char_count > 10:
        length_factor = 10 / city_char_count
        adjusted_font_size = max(base_adjusted_main * length_factor, 10 * scale_factor)
    else:
        adjusted_font_size = base_adjusted_main

    if active_fonts:
        font_main_adjusted = FontProperties(
            fname=active_fonts["bold"], size=adjusted_font_size
        )
    else:
        font_main_adjusted = FontProperties(
            family="monospace", weight="bold", size=adjusted_font_size
        )

    if text_options == "keep_all":
        # --- BOTTOM TEXT ---
        ax.text(
            0.5,
            0.14,
            spaced_city,
            transform=ax.transAxes,
            color=THEME["text"],
            ha="center",
            fontproperties=font_main_adjusted,
            zorder=11,
        )

        ax.text(
            0.5,
            0.10,
            display_country.upper(),
            transform=ax.transAxes,
            color=THEME["text"],
            ha="center",
            fontproperties=font_sub,
            zorder=11,
            )

        lat, lon = point
        coords = (
            f"{lat:.4f}° N / {lon:.4f}° E"
            if lat >= 0
            else f"{abs(lat):.4f}° S / {lon:.4f}° E"
        )
        if lon < 0:
            coords = coords.replace("E", "W")

        ax.text(
            0.5,
            0.07,
            coords,
            transform=ax.transAxes,
            color=THEME["text"],
            alpha=0.7,
            ha="center",
            fontproperties=font_coords,
            zorder=11,
        )

        ax.plot(
            [0.4, 0.6],
            [0.125, 0.125],
            transform=ax.transAxes,
            color=THEME["text"],
            linewidth=1 * scale_factor,
            zorder=11,
        )
    if text_options == "no_coords": 
        ax.text(
            0.5,
            0.14,
            spaced_city,
            transform=ax.transAxes,
            color=THEME["text"],
            ha="center",
            fontproperties=font_main_adjusted,
            zorder=11,
        )

        ax.text(
            0.5,
            0.10,
            display_country.upper(),
            transform=ax.transAxes,
            color=THEME["text"],
            ha="center",
            fontproperties=font_sub,
            zorder=11,
        )
        
        ax.plot(
            [0.4, 0.6],
            [0.125, 0.125],
            transform=ax.transAxes,
            color=THEME["text"],
            linewidth=1 * scale_factor,
            zorder=11,
        )
    if text_options == "no_country": 
         # --- BOTTOM TEXT ---
        ax.text(
            0.5,
            0.14,
            spaced_city,
            transform=ax.transAxes,
            color=THEME["text"],
            ha="center",
            fontproperties=font_main_adjusted,
            zorder=11,
        )

        lat, lon = point
        coords = (
            f"{lat:.4f}° N / {lon:.4f}° E"
            if lat >= 0
            else f"{abs(lat):.4f}° S / {lon:.4f}° E"
        )
        if lon < 0:
            coords = coords.replace("E", "W")

        ax.text(
            0.5,
            0.10,
            coords,
            transform=ax.transAxes,
            color=THEME["text"],
            alpha=0.7,
            ha="center",
            fontproperties=font_coords,
            zorder=11,
        )

        ax.plot(
            [0.4, 0.6],
            [0.125, 0.125],
            transform=ax.transAxes,
            color=THEME["text"],
            linewidth=1 * scale_factor,
            zorder=11,
        )
    if text_options == "no_city_country":
        lat, lon = point
        coords = (
            f"{lat:.4f}° N / {lon:.4f}° E"
            if lat >= 0
            else f"{abs(lat):.4f}° S / {lon:.4f}° E"
        )
        if lon < 0:
            coords = coords.replace("E", "W")

        ax.text(
            0.5,
            0.14,
            coords,
            transform=ax.transAxes,
            color=THEME["text"],
            alpha=0.7,
            ha="center",
            fontproperties=font_main_adjusted,
            zorder=11,
        )
    if text_options == "clear_all": ()
 

    # --- ATTRIBUTION (bottom right) ---
    if FONTS:
        font_attr = FontProperties(fname=FONTS["light"], size=8)
    else:
        font_attr = FontProperties(family="monospace", size=8)

    ax.text(
        0.98,
        0.02,
        "© OpenStreetMap contributors",
        transform=ax.transAxes,
        color=THEME["text"],
        alpha=0.5,
        ha="right",
        va="bottom",
        fontproperties=font_attr,
        zorder=11,
    )

    # 5. Save
    print(f"Saving to {output_file}...")

    fmt = output_format.lower()
    save_kwargs = dict(
        facecolor=THEME["bg"],
        bbox_inches="tight",
        pad_inches=0.05,
    )

    # DPI matters mainly for raster formats
    if fmt == "png":
        save_kwargs["dpi"] = 300

    plt.savefig(output_file, format=fmt, **save_kwargs)

    plt.close()
    print(f"✓ Done! Poster saved as {output_file}")


def print_examples():
    """Print usage examples."""
    print("""
City Map Poster Generator
=========================

Usage:
  python create_map_poster.py --city <city> --country <country> [options]

Examples:
  # Iconic grid patterns
  python create_map_poster.py -c "New York" -C "USA" -t noir -d 12000           # Manhattan grid
  python create_map_poster.py -c "Barcelona" -C "Spain" -t warm_beige -d 8000   # Eixample district grid

  # Waterfront & canals
  python create_map_poster.py -c "Venice" -C "Italy" -t blueprint -d 4000       # Canal network
  python create_map_poster.py -c "Amsterdam" -C "Netherlands" -t ocean -d 6000  # Concentric canals
  python create_map_poster.py -c "Dubai" -C "UAE" -t midnight_blue -d 15000     # Palm & coastline

  # Radial patterns
  python create_map_poster.py -c "Paris" -C "France" -t pastel_dream -d 10000   # Haussmann boulevards
  python create_map_poster.py -c "Moscow" -C "Russia" -t noir -d 12000          # Ring roads

  # Organic old cities
  python create_map_poster.py -c "Tokyo" -C "Japan" -t japanese_ink -d 15000    # Dense organic streets
  python create_map_poster.py -c "Marrakech" -C "Morocco" -t terracotta -d 5000 # Medina maze
  python create_map_poster.py -c "Rome" -C "Italy" -t warm_beige -d 8000        # Ancient street layout

  # Coastal cities
  python create_map_poster.py -c "San Francisco" -C "USA" -t sunset -d 10000    # Peninsula grid
  python create_map_poster.py -c "Sydney" -C "Australia" -t ocean -d 12000      # Harbor city
  python create_map_poster.py -c "Mumbai" -C "India" -t contrast_zones -d 18000 # Coastal peninsula

  # River cities
  python create_map_poster.py -c "London" -C "UK" -t noir -d 15000              # Thames curves
  python create_map_poster.py -c "Budapest" -C "Hungary" -t copper_patina -d 8000  # Danube split

  # List themes
  python create_map_poster.py --list-themes

Options:
  --city, -c        City name (required)
  --country, -C     Country name (required)
  --country-label   Override country text displayed on poster
  --theme, -t       Theme name (default: terracotta)
  --all-themes      Generate posters for all themes
  --distance, -d    Map radius in meters (default: 18000)
  --list-themes     List all available themes
  --text-options    Enables user to decide if and which texts to print to poster

Distance guide:
  4000-6000m   Small/dense cities (Venice, Amsterdam old center)
  8000-12000m  Medium cities, focused downtown (Paris, Barcelona)
  15000-20000m Large metros, full city view (Tokyo, Mumbai)

Available themes can be found in the 'themes/' directory.
Generated posters are saved to 'posters/' directory.
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate beautiful map posters for any city",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_map_poster.py --city "New York" --country "USA"
  python create_map_poster.py --city "New York" --country "USA" -l 40.776676 -73.971321 --theme neon_cyberpunk
  python create_map_poster.py --city Tokyo --country Japan --theme midnight_blue
  python create_map_poster.py --city Paris --country France --theme noir --distance 15000
  python create_map_poster.py --list-themes
        """,
    )

    parser.add_argument("--city", "-c", type=str, help="City name")
    parser.add_argument("--country", "-C", type=str, help="Country name")
    parser.add_argument(
        "--latitude",
        "-lat",
        dest="latitude",
        type=str,
        help="Override latitude center point",
    )
    parser.add_argument(
        "--longitude",
        "-long",
        dest="longitude",
        type=str,
        help="Override longitude center point",
    )
    parser.add_argument(
        "--country-label",
        dest="country_label",
        type=str,
        help="Override country text displayed on poster",
    )
    parser.add_argument(
        "--theme",
        "-t",
        type=str,
        default="terracotta",
        help="Theme name (default: terracotta)",
    )
    parser.add_argument(
        "--all-themes",
        "--All-themes",
        dest="all_themes",
        action="store_true",
        help="Generate posters for all themes",
    )
    parser.add_argument(
        "--distance",
        "-d",
        type=int,
        default=18000,
        help="Map radius in meters (default: 18000)",
    )
    parser.add_argument(
        "--width",
        "-W",
        type=float,
        default=12,
        help="Image width in inches (default: 12, max: 20 )",
    )
    parser.add_argument(
        "--height",
        "-H",
        type=float,
        default=16,
        help="Image height in inches (default: 16, max: 20)",
    )
    parser.add_argument(
        "--list-themes", action="store_true", help="List all available themes"
    )
    parser.add_argument(
        "--display-city",
        "-dc",
        type=str,
        help="Custom display name for city (for i18n support)",
    )
    parser.add_argument(
        "--display-country",
        "-dC",
        type=str,
        help="Custom display name for country (for i18n support)",
    )
    parser.add_argument(
        "--font-family",
        type=str,
        help='Google Fonts family name (e.g., "Noto Sans JP", "Open Sans"). If not specified, uses local Roboto fonts.',
    )
    parser.add_argument(
        "--format",
        "-f",
        default="png",
        choices=["png", "svg", "pdf"],
        help="Output format for the poster (default: png)",
    )
    parser.add_argument(
        '--text-options',
        default="keep_all",
        choices=["keep_all", "clear_all", "no_coords", "no_country", "no_city_country"],
        help='Different options for texts displayed on the generated poster.'
    )

    args = parser.parse_args()

    # If no arguments provided, show examples
    if len(sys.argv) == 1:
        print_examples()
        sys.exit(0)

    # List themes if requested
    if args.list_themes:
        list_themes()
        sys.exit(0)

    # Validate required arguments
    if not args.city or not args.country:
        print("Error: --city and --country are required.\n")
        print_examples()
        sys.exit(1)

    # Enforce maximum dimensions
    if args.width > 20:
        print(
            f"⚠ Width {args.width} exceeds the maximum allowed limit of 20. It's enforced as max limit 20."
        )
        args.width = 20.0
    if args.height > 20:
        print(
            f"⚠ Height {args.height} exceeds the maximum allowed limit of 20. It's enforced as max limit 20."
        )
        args.height = 20.0

    available_themes = get_available_themes()
    if not available_themes:
        print("No themes found in 'themes/' directory.")
        sys.exit(1)

    if args.all_themes:
        themes_to_generate = available_themes
    else:
        if args.theme not in available_themes:
            print(f"Error: Theme '{args.theme}' not found.")
            print(f"Available themes: {', '.join(available_themes)}")
            sys.exit(1)
        themes_to_generate = [args.theme]

    print("=" * 50)
    print("City Map Poster Generator")
    print("=" * 50)

    # Load custom fonts if specified
    custom_fonts = None
    if args.font_family:
        custom_fonts = load_fonts(args.font_family)
        if not custom_fonts:
            print(f"⚠ Failed to load '{args.font_family}', falling back to Roboto")

    # Get coordinates and generate poster
    try:
        if args.latitude and args.longitude:
            lat = parse(args.latitude)
            lon = parse(args.longitude)
            coords = [lat, lon]
            print(f"✓ Coordinates: {', '.join([str(i) for i in coords])}")
        else:
            coords = get_coordinates(args.city, args.country)

        for theme_name in themes_to_generate:
            THEME = load_theme(theme_name)
            output_file = generate_output_filename(args.city, theme_name, args.format)
            create_poster(
                args.city,
                args.country,
                coords,
                args.distance,
                output_file,
                args.format,    
                args.text_options,
                args.width,
                args.height,
                country_label=args.country_label,
                display_city=args.display_city,
                display_country=args.display_country,
                fonts=custom_fonts,
            )

        print("\n" + "=" * 50)
        print("✓ Poster generation complete!")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
