import os
import sys
import db_schema
import json
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import argparse
from scraper import (
    scrape_listings,
    preview_url_listings_count,
    harvest_descriptions,
    update_all_descriptions_session,
)

# Set up logging to both console and file
log_file = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "scraper.log",
)
os.makedirs(os.path.dirname(log_file), exist_ok=True)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear existing handlers to prevent duplicate logs
for handler in list(root_logger.handlers):
    root_logger.removeHandler(handler)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# File handler with rotation (max 5MB, keep 3 backups)
file_handler = RotatingFileHandler(
    log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

DB_PATH = db_schema.default_path()


def get_db_connection():
    return sqlite3.connect(DB_PATH)


def annotate_route_detours(conn, campaign_id=None):
    """Computes detours for every route search that has listings waiting.

    Deliberately forgiving: a route whose routing fails is logged and the rest
    still run. The detour is an enrichment, and an enrichment must never be able
    to fail a scrape that already succeeded.
    """
    try:
        import route_pipeline
        import route_store

        route_store.ensure_schema(conn)
        if campaign_id is None:
            rows = conn.execute("SELECT id, name FROM route_searches").fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name FROM route_searches WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchall()
    except Exception as exc:
        logger.info("No route searches to annotate (%s).", exc)
        return

    for row in rows:
        route_id, name = row[0], row[1]
        try:
            summary = route_pipeline.annotate(conn, route_id)
            if summary["considered"]:
                logger.info("Route %s (%s): %s", route_id, name, summary)
        except Exception as exc:
            logger.warning(
                "Could not compute detours for route %s (%s): %s. Listings are "
                "stored; the next run will try again.",
                route_id,
                name,
                exc,
            )


def run_route_mode(args):
    """Plans a route corridor, or computes detours for one already planned.

    Creation and annotation are separate commands because they belong to
    different moments: a corridor is planned once, when a buyer says where they
    are driving, and its circles are then scraped like any other search. Detours
    are computed afterwards, so the routing service never sits in the scraper's
    path — if it is unreachable, listings still arrive, only without a detour.
    """
    import route_pipeline

    if args.mode == "route-preview":
        if not args.origin or not args.destination:
            logger.error("route-preview needs --from and --to")
            return
        if not args.urls:
            logger.error("route-preview needs --urls with one search URL")
            return

        import json as _json

        import route_search
        import routing

        client = routing.OsrmClient()
        try:
            # Same resolution the real creation uses, so what is drawn is what
            # would be built — a preview that plans a different route than the
            # commit would is worse than no preview.
            start = route_pipeline.resolve_place(args.origin)
            end = route_pipeline.resolve_place(args.destination)
            plan = route_search.plan(
                args.urls[0],
                client.route([start, end]),
                radius_km=args.radius_km,
                half_width_km=args.corridor_km,
            )
        except ValueError as error:
            print(f"__ROUTE_PREVIEW_ERROR__:{error}")
            return

        payload = plan.as_dict()
        # The polyline is thousands of points and a map does not need them all;
        # what the caller is drawing is the shape, not the kerb.
        payload["polyline"] = _thin(payload["polyline"], 400)
        payload.pop("segment_durations", None)
        print("__ROUTE_PREVIEW__:" + _json.dumps(payload))
        return

    conn = get_db_connection()

    if args.mode == "route-replan":
        if not args.route_id:
            logger.error("route-replan needs --route-id")
            return
        try:
            kept, added, removed, plan = route_pipeline.replan(
                conn,
                args.route_id,
                radius_km=args.radius_km,
                half_width_km=args.corridor_km,
            )
        except ValueError as error:
            print(f"__ROUTE_REPLAN_ERROR__:{error}")
            return
        print(f"__ROUTE_REPLANNED__:{kept} kept, {added} added, {removed} removed")
        for index, circle in enumerate(plan.circles, 1):
            print(f"  {index}. r{circle.radius_km:<3} {circle.label}")
        return

    if args.mode == "route-create":
        if not args.origin or not args.destination:
            logger.error("route-create needs --from and --to")
            return
        if not args.urls:
            logger.error(
                "route-create needs --urls with one search URL to re-aim along "
                "the route, e.g. a Kleinanzeigen search ending in k0l...r..."
            )
            return

        route_id, plan = route_pipeline.create(
            conn,
            base_url=args.urls[0],
            origin=args.origin,
            destination=args.destination,
            radius_km=args.radius_km,
            half_width_km=args.corridor_km,
            name=args.route_name,
            campaign_id=args.campaign_id,
            knowledge_set_id=args.knowledge_set_id,
        )
        print(f"__ROUTE_ID__:{route_id}")
        for index, circle in enumerate(plan.circles, 1):
            print(f"  {index}. r{circle.radius_km:<3} {circle.label}")
            print(f"     {circle.url}")
        if plan.unresolved:
            logger.warning(
                "No location id for these postal codes, so their circles were "
                "skipped: %s",
                ", ".join(plan.unresolved),
            )
        return

    if not args.route_id:
        logger.error("route-annotate needs --route-id")
        return

    summary = route_pipeline.annotate(conn, args.route_id)
    print(
        f"__ROUTE_ANNOTATED__:{summary['routed']}/{summary['considered']} "
        f"(too far: {summary['too_far']}, unplaceable: {summary['unplaceable']})"
    )


def _thin(points, limit):
    """Every nth point, keeping both ends. A map draws the shape, not the kerb."""
    if len(points) <= limit:
        return points
    step = len(points) / float(limit)
    thinned = [points[int(index * step)] for index in range(limit)]
    if thinned[-1] != points[-1]:
        thinned.append(points[-1])
    return thinned


def main():
    """Main entry point that acts as a wrapper for different functionalities"""
    parser = argparse.ArgumentParser(
        description="Multi-Domain Expert scraper and processor"
    )
    parser.add_argument(
        "--mode",
        choices=[
            "scrape",
            "process",
            "both",
            "preview",
            "update-all",
            "route-preview",
            "route-replan",
            "route-create",
            "route-annotate",
        ],
        default="both",
        help=(
            "Operation mode: scrape, process, both, preview, update-all, "
            "route-preview, route-create, or route-annotate"
        ),
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        default=None,
        help="Specific URLs to scrape (overrides DB search list)",
    )
    parser.add_argument(
        "--max-listings",
        type=int,
        default=None,
        help="Maximum number of listings to scrape per URL",
    )
    parser.add_argument(
        "--listing-id",
        type=str,
        default=None,
        help="Specific listing ID to process",
    )
    parser.add_argument(
        "--search-id",
        type=int,
        default=None,
        help="Search ID to associate the scraped listings with",
    )
    parser.add_argument(
        "--campaign-id",
        type=int,
        default=None,
        help="Campaign ID to filter searches, description updates, and AI matching",
    )

    # --- route search --------------------------------------------------
    route = parser.add_argument_group(
        "route search",
        "Search along a route instead of around a point. A corridor is covered "
        "by the fewest circles that reach its edges, each registered as an "
        "ordinary search; detours are computed afterwards with route-annotate.",
    )
    route.add_argument(
        "--from",
        dest="origin",
        help="Where the trip starts: a postal code, or 'Ort, Bundesland'",
    )
    route.add_argument(
        "--to",
        dest="destination",
        help="Where it ends: a postal code, or 'Ort, Bundesland'",
    )
    route.add_argument(
        "--radius-km",
        type=float,
        default=30.0,
        help="Search radius per circle (default: 30)",
    )
    route.add_argument(
        "--corridor-km",
        type=float,
        default=15.0,
        help="How far off the route to search, each side (default: 15)",
    )
    route.add_argument(
        "--knowledge-set-id",
        type=int,
        default=None,
        help="Knowledge set the corridor's searches are scored against",
    )
    route.add_argument(
        "--route-id",
        type=int,
        default=None,
        help="Route search to annotate with detours",
    )
    route.add_argument(
        "--route-name",
        default=None,
        help="Label for this route search",
    )

    args = parser.parse_args()

    if args.mode in (
        "route-preview",
        "route-replan",
        "route-create",
        "route-annotate",
    ):
        run_route_mode(args)
        return

    if args.mode == "preview":
        if not args.urls or len(args.urls) == 0:
            print("__PREVIEW_ERROR__:No target URL provided")
            return
        preview_url_listings_count(args.urls[0])
        return

    if args.mode == "update-all":
        logger.info("Executing deep update of existing descriptions...")
        try:
            update_all_descriptions_session(args.campaign_id)
            logger.info("Deep updates completed successfully.")
        except Exception as e:
            logger.error(f"Error during deep updates: {str(e)}")
        return

    # Define paths for data
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
    temp_output_file = os.path.join(data_dir, "temp_scraped.json")

    # Create data directory if it doesn't exist
    os.makedirs(data_dir, exist_ok=True)

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Scraping Mode
    if args.mode in ["scrape", "both"]:
        logger.info("Starting dynamic scraping mode")

        # Load targets from database
        search_targets = []
        if args.urls is not None:
            # Overridden via command line arguments
            for url in args.urls:
                search_targets.append({"url": url, "search_id": args.search_id})
        else:
            try:
                if args.campaign_id is not None:
                    cursor.execute(
                        "SELECT id, url FROM searches WHERE enabled = 1 AND campaign_id = ?",
                        (args.campaign_id,),
                    )
                else:
                    cursor.execute("SELECT id, url FROM searches WHERE enabled = 1")
                rows = cursor.fetchall()
                for r in rows:
                    search_targets.append({"url": r["url"], "search_id": r["id"]})
                logger.info(
                    f"Loaded {len(search_targets)} active search URLs from SQLite"
                )
            except Exception as e:
                logger.error(f"Error querying search URLs from DB: {str(e)}")

        # Fallback to default if absolutely no searches exist
        if not search_targets:
            default_url = (
                "https://www.kleinanzeigen.de/s-notebooks/preis::1400/rtx4060/k0c278"
            )
            search_targets.append({"url": default_url, "profile_id": None})
            logger.info(f"Using default search URL: {default_url}")

        for target in search_targets:
            url = target["url"]
            search_id = target.get("search_id")

            logger.info(f"Scraping search target: {url}")

            # Clean up temp file before scraping this target
            if os.path.exists(temp_output_file):
                try:
                    os.remove(temp_output_file)
                except OSError:
                    pass

            try:
                # Scrape listings to temp JSON file
                scrape_listings(
                    [url],
                    temp_output_file,
                    max_listings=args.max_listings,
                )

                # Import scraped items into SQLite
                if os.path.exists(temp_output_file):
                    with open(temp_output_file, "r", encoding="utf-8") as f:
                        scraped_items = json.load(f)

                    logger.info(
                        f"Importing {len(scraped_items)} listings into database..."
                    )

                    for item in scraped_items:
                        listing_id = item.get("id")
                        if not listing_id:
                            continue

                        # Insert or ignore to prevent duplicates
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO listings (
                                id, title, price, location, url, short_description, detailed_description, search_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                listing_id,
                                item.get("title", ""),
                                item.get("price", ""),
                                item.get("location", ""),
                                item.get("url", ""),
                                item.get("short_description", ""),
                                item.get("detailed_description", ""),
                                search_id,
                            ),
                        )
                    conn.commit()
            except Exception as e:
                logger.error(f"Error scraping or importing URL {url}: {str(e)}")

        # 1.5. Sequential detailed description harvesting phase
        logger.info("Executing optimized sequential detailed description harvesting...")
        try:
            harvest_descriptions(args.campaign_id)
            logger.info("Description harvesting completed successfully.")
        except Exception as e:
            logger.error(f"Error during detailed description harvesting: {str(e)}")

        # 1.6. Detours for anything collected along a route.
        #
        # After the scrape, never during it. A listing's detour is worth having
        # but is never worth losing a listing over, so a routing service that is
        # slow or down must not be able to reach the fetching loop. Failures here
        # leave listings in place without a detour; the next run picks them up.
        annotate_route_detours(conn, args.campaign_id)

    # 2. Processing Mode
    if args.mode in ["process", "both"]:
        # Playbook-backed categories run through the decoupled pipeline first:
        # it extracts one fact sheet per listing and scores every buyer against
        # it without further model calls. Listings it handles are marked
        # processed, so the legacy worker below only picks up the remainder.
        try:
            import pipeline

            outcomes = pipeline.run(conn, pipeline.default_model_caller())
            stats = pipeline.summarise(outcomes)
            if stats["processed"]:
                logger.info(
                    "Pipeline: %d listing(s) processed, %d model call(s), "
                    "%d served from fact-sheet cache, %d identity/identities resolved.",
                    stats["processed"],
                    stats["model_calls"],
                    stats["from_cache"],
                    stats["identities_resolved"],
                )
            for reason, count in stats["skip_reasons"].items():
                logger.info(
                    "Pipeline left %d listing(s) to the legacy worker (%s).",
                    count,
                    reason,
                )
        except Exception as e:
            logger.error(f"Playbook pipeline failed, falling back entirely: {str(e)}")

        logger.info("Starting processing mode via agent_worker...")
        conn.close()  # Close connection to prevent sqlite locks during process spawn

        # Run agent_worker process command
        import subprocess

        try:
            worker_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "agent_worker.py"
            )
            # sys.executable, not a bare "python3": the worker's dependencies
            # (openai, ...) live in this project's venv, and a bare name resolves
            # against PATH, which lands on the system interpreter instead.
            cmd = [sys.executable, worker_path, "process"]
            if args.listing_id:
                cmd.append(args.listing_id)
            if args.campaign_id is not None:
                cmd.extend(["--campaign-id", str(args.campaign_id)])
            subprocess.run(cmd, check=True)
            logger.info("Successfully executed agent_worker processing.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running agent_worker process: {str(e)}")

    # Cleanup temp file
    if os.path.exists(temp_output_file):
        try:
            os.remove(temp_output_file)
        except OSError:
            pass

    logger.info("All operations completed.")


if __name__ == "__main__":
    main()
