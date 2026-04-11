import os
import sys
import json
import logging
import requests
import math
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] %(message)s")
logger = logging.getLogger("DecisionProxy")

OVERPASS_URL = "http://overpass-api.de/api/interpreter"

# SFH/MFH Signal Thresholds
SFH_MAX_AREA = 150.0   # small footprint indicates SFH
MFH_MIN_AREA = 400.0   # large footprint indicates MFH/Apartment block

SFH_TAGS = {"house", "detached", "semidetached_house", "terrace", "bungalow"}
MFH_TAGS = {"apartments", "dormitory", "hotel"}
NEUTRAL_TAGS = {"residential", "yes", "building"}

def get_polygon_area(geometry):
    # Apply Shoelace theorem after local Cartesian projection
    if not geometry or len(geometry) < 3:
        return 0.0
    
    # 1 deg lat = ~111,320m. 1 deg lon = ~111,320m * cos(lat)
    pts = []
    for node in geometry:
        # Assuming format { 'lat': lat, 'lon': lon }
        lat, lon = node['lat'], node['lon']
        y = lat * 111320.0
        x = lon * 111320.0 * math.cos(math.radians(lat))
        pts.append((x, y))
        
    area = 0.0
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0

def fetch_neuss_building_geoms():
    query = """
    [out:json][timeout:90];
    (
      way["building"~"residential|house|apartments|detached|semi|terrace"](51.13, 6.61, 51.25, 6.77);
    );
    out geom tags;
    """
    logger.info("Executing isolated Overpass API Query for Neuss geometries...")
    resp = requests.post(OVERPASS_URL, data={"data": query})
    if resp.status_code != 200:
        logger.error(f"Overpass API returned {resp.status_code}")
        sys.exit(1)
    return resp.json().get("elements", [])

def main():
    logger.info("Starting Lightweight SFH/MFH Decision-Structure Proxy")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clusters_file = os.path.join(base_dir, "output", "clusters", "neuss_hybrid_clusters_v1.json")
    
    if not os.path.exists(clusters_file):
        logger.error("Base MVP cluster feed not found. Run generate_neuss_osm_clusters.py first.")
        sys.exit(1)
        
    with open(clusters_file, 'r', encoding='utf-8') as f:
        existing_clusters = json.load(f)
        
    # Build a lookup map: (primary_street, segment_id -> cluster_id)
    # Actually, the base generator groups by street + plz.
    # Let's map buildings to streets. We will rely on matching the street name to our MVP feed.
    valid_streets = {c["primary_street"] for c in existing_clusters}
    
    elements = fetch_neuss_building_geoms()
    logger.info(f"Retrieved {len(elements)} geometry elements.")
    
    # Aggregate signals at street level
    street_stats = {}
    for el in elements:
        tags = el.get("tags", {})
        street = tags.get("addr:street")
        if not street or street not in valid_streets:
            continue
            
        geom = el.get("geometry", [])
        area = get_polygon_area(geom)
        if area == 0.0:
            continue
            
        if street not in street_stats:
            street_stats[street] = {
                "b_count": 0, "areas": [], 
                "sfh_tag_c": 0, "mfh_tag_c": 0, "neutral_tag_c": 0,
                "low_rise_c": 0, "high_rise_c": 0, "level_known_c": 0
            }
        
        st = street_stats[street]
        st["b_count"] += 1
        st["areas"].append(area)
        
        b_type = tags.get("building", "").lower()
        if b_type in SFH_TAGS: st["sfh_tag_c"] += 1
        elif b_type in MFH_TAGS: st["mfh_tag_c"] += 1
        else: st["neutral_tag_c"] += 1
            
        levels_str = tags.get("building:levels")
        if levels_str and levels_str.isdigit():
            lv = int(levels_str)
            st["level_known_c"] += 1
            if lv <= 2: st["low_rise_c"] += 1
            elif lv >= 4: st["high_rise_c"] += 1
            
    logger.info("Polygons processed and mapped to MVP streets.")
    
    # Generate Proxy Outputs
    proxy_rows = []
    
    for c in existing_clusters:
        c_id = c["cluster_id"]
        street = c["primary_street"]
        lead_count = c["lead_count"]
        
        st = street_stats.get(street)
        if not st or st["b_count"] == 0:
            # Ambiguous due to no matching geometries
            proxy_rows.append({
                "cluster_id": c_id, "street_name": street, "building_count": lead_count,
                "median_footprint_m2": 0, "small_footprint_ratio": 0, "large_footprint_ratio": 0,
                "sfh_tag_ratio": 0, "mfh_tag_ratio": 0, "low_rise_ratio": 0, "high_rise_ratio": 0,
                "sfh_like_score": 0.0, "mfh_like_score": 0.0,
                "decision_structure_class": "AMBIGUOUS", "confidence": "LOW_CONFIDENCE",
                "notes": "No geometry mapped"
            })
            continue

        areas = sorted(st["areas"])
        med_area = areas[len(areas)//2]
        small_r = sum(1 for a in areas if a < SFH_MAX_AREA) / len(areas)
        large_r = sum(1 for a in areas if a > MFH_MIN_AREA) / len(areas)
        
        sfh_tag_r = st["sfh_tag_c"] / st["b_count"]
        mfh_tag_r = st["mfh_tag_c"] / st["b_count"]
        
        low_rise_r = st["low_rise_c"] / st["level_known_c"] if st["level_known_c"] > 0 else 0.0
        high_rise_r = st["high_rise_c"] / st["level_known_c"] if st["level_known_c"] > 0 else 0.0
        
        # Calculate dynamic weighted score avoiding missing data penalty
        # Weight pools: Footprint=0.5, Tag=0.3, Levels=0.2
        sfh_w_sum = 0.5 * small_r + 0.3 * sfh_tag_r
        mfh_w_sum = 0.5 * large_r + 0.3 * mfh_tag_r
        
        avail_weight = 0.8
        if st["level_known_c"] > 0:
            sfh_w_sum += 0.2 * low_rise_r
            mfh_w_sum += 0.2 * high_rise_r
            avail_weight += 0.2
            
        sfh_score = sfh_w_sum / avail_weight
        mfh_score = mfh_w_sum / avail_weight
        
        decision = "AMBIGUOUS"
        if sfh_score > 0.55 and sfh_score > mfh_score + 0.15:
            decision = "SFH_LIKELY"
        elif mfh_score > 0.55 and mfh_score > sfh_score + 0.15:
            decision = "MFH_LIKELY"
            
        gap = abs(sfh_score - mfh_score)
        if gap > 0.3 or max(sfh_score, mfh_score) > 0.75:
            conf = "HIGH_CONFIDENCE"
        elif gap > 0.15:
            conf = "MEDIUM_CONFIDENCE"
        else:
            conf = "LOW_CONFIDENCE"
            
        # Optional: Aspect ratio diagnostic
        # Excluded from calculation per user direction, but useful note
        note = f"{len(areas)} areas parsed."
        
        proxy_rows.append({
            "cluster_id": c_id, "street_name": street, "building_count": len(areas),
            "median_footprint_m2": round(med_area, 1), 
            "small_footprint_ratio": round(small_r, 2), "large_footprint_ratio": round(large_r, 2),
            "sfh_tag_ratio": round(sfh_tag_r, 2), "mfh_tag_ratio": round(mfh_tag_r, 2), 
            "low_rise_ratio": round(low_rise_r, 2), "high_rise_ratio": round(high_rise_r, 2),
            "sfh_like_score": round(sfh_score, 3), "mfh_like_score": round(mfh_score, 3),
            "decision_structure_class": decision, "confidence": conf,
            "notes": note
        })

    proxy_dir = os.path.join(base_dir, "output", "proxy")
    os.makedirs(proxy_dir, exist_ok=True)
    
    df = pd.DataFrame(proxy_rows)
    df.to_csv(os.path.join(proxy_dir, "sfh_mfh_cluster_proxy_summary.csv"), index=False)
    
    # Candidate lists
    sfh_df = df[df["decision_structure_class"] == "SFH_LIKELY"].sort_values("sfh_like_score", ascending=False)
    sfh_df.to_csv(os.path.join(proxy_dir, "candidate_sfh_majority.csv"), index=False)
    
    mfh_df = df[df["decision_structure_class"] == "MFH_LIKELY"].sort_values("mfh_like_score", ascending=False)
    mfh_df.to_csv(os.path.join(proxy_dir, "candidate_mfh_majority.csv"), index=False)
    
    amb_df = df[df["decision_structure_class"] == "AMBIGUOUS"]
    amb_df.to_csv(os.path.join(proxy_dir, "candidate_ambiguous.csv"), index=False)
    
    logger.info(f"Proxy Complete. Found {len(sfh_df)} SFH, {len(mfh_df)} MFH, {len(amb_df)} Ambiguous.")

if __name__ == "__main__":
    main()
