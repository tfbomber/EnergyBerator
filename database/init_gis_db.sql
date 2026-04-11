-- ==========================================
-- D-ESS Neuss GIS & Campaign Engine
-- Database Initialization Script (v1.0)
-- Target: PostgreSQL + PostGIS
-- ==========================================

-- 1. Enable Spatial Extensions
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Create Schema Architecture
CREATE SCHEMA IF NOT EXISTS raw;     -- Ingested source snapshots
CREATE SCHEMA IF NOT EXISTS core;    -- Master geography (Spatial Spine)
CREATE SCHEMA IF NOT EXISTS feature; -- Engineered business features (Level A/B)
CREATE SCHEMA IF NOT EXISTS output;  -- Campaign snapshots & marketing payloads
CREATE SCHEMA IF NOT EXISTS audit;   -- Lineage, logs, and versioning

-- ==========================================
-- AUDIT SCHEMA
-- ==========================================

CREATE TABLE audit.source_registry (
    source_id VARCHAR(128) PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) CHECK (source_type IN ('API', 'DUMP', 'SCRAPE', 'MANUAL')),
    source_scope VARCHAR(100),
    source_url_or_ref TEXT,
    freshness_date DATE,
    ingestion_method VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit.data_version_registry (
    data_version VARCHAR(128) PRIMARY KEY, -- e.g., 'NEUSS_V1_202603'
    city_scope VARCHAR(128) NOT NULL,
    description TEXT,
    source_snapshot_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit.ingestion_log (
    ingestion_log_id VARCHAR(128) PRIMARY KEY,
    source_id VARCHAR(128) REFERENCES audit.source_registry(source_id),
    data_version VARCHAR(128) REFERENCES audit.data_version_registry(data_version),
    ingestion_started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ingestion_finished_at TIMESTAMP WITH TIME ZONE,
    row_count INTEGER,
    status VARCHAR(50) CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL')),
    error_message TEXT
);

CREATE TABLE audit.aggregation_log (
    aggregation_log_id VARCHAR(128) PRIMARY KEY,
    data_version VARCHAR(128) REFERENCES audit.data_version_registry(data_version),
    segment_id VARCHAR(128) NOT NULL, -- Logical ref to core.street_segment
    aggregation_method VARCHAR(100),
    input_building_count INTEGER,
    output_status VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE TABLE audit.model_run_log (
    model_run_id VARCHAR(128) PRIMARY KEY,
    segment_id VARCHAR(128) NOT NULL,
    data_version VARCHAR(128) REFERENCES audit.data_version_registry(data_version),
    policy_version VARCHAR(50) NOT NULL,
    roi_engine_version VARCHAR(50) NOT NULL,
    run_started_at TIMESTAMP WITH TIME ZONE,
    run_finished_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    notes TEXT
);

-- ==========================================
-- CORE SCHEMA (The Spatial Spine)
-- ==========================================

CREATE TABLE core.city (
    city_id VARCHAR(128) PRIMARY KEY, -- e.g. DE_NRW_NEUSS
    city_name VARCHAR(255) NOT NULL,
    state_code VARCHAR(10),
    country_code VARCHAR(10) DEFAULT 'DE',
    geom Geometry(MultiPolygon, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_city_geom ON core.city USING GIST (geom);

CREATE TABLE core.stadtteil (
    stadtteil_id VARCHAR(128) PRIMARY KEY, -- e.g. DE_NRW_NEUSS_ALLERHEILIGEN
    city_id VARCHAR(128) REFERENCES core.city(city_id),
    stadtteil_name VARCHAR(255) NOT NULL,
    postal_code VARCHAR(10),
    geom Geometry(MultiPolygon, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_stadtteil_geom ON core.stadtteil USING GIST (geom);

CREATE TABLE core.street (
    street_id VARCHAR(128) PRIMARY KEY, 
    city_id VARCHAR(128) REFERENCES core.city(city_id),
    stadtteil_id VARCHAR(128) REFERENCES core.stadtteil(stadtteil_id),
    street_name VARCHAR(255) NOT NULL,
    postal_code VARCHAR(10),
    geom Geometry(MultiLineString, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_street_geom ON core.street USING GIST (geom);

CREATE TABLE core.street_segment (
    segment_id VARCHAR(128) PRIMARY KEY, -- e.g. ..._SEG_01
    city_id VARCHAR(128) REFERENCES core.city(city_id),
    stadtteil_id VARCHAR(128) REFERENCES core.stadtteil(stadtteil_id),
    street_id VARCHAR(128) REFERENCES core.street(street_id),
    segment_name VARCHAR(255) NOT NULL,
    segment_seq INTEGER NOT NULL,
    from_house_no VARCHAR(20),
    to_house_no VARCHAR(20),
    side_of_street VARCHAR(10) CHECK (side_of_street IN ('ODD', 'EVEN', 'BOTH', 'UNKNOWN')),
    segment_rule VARCHAR(100),
    status VARCHAR(50) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'RETIRED', 'MERGED', 'SPLIT')),
    geom Geometry(MultiLineString, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_segment_geom ON core.street_segment USING GIST (geom);
CREATE INDEX idx_segment_street_id ON core.street_segment (street_id);

CREATE TABLE core.building (
    building_id VARCHAR(128) PRIMARY KEY,
    city_id VARCHAR(128) REFERENCES core.city(city_id),
    stadtteil_id VARCHAR(128) REFERENCES core.stadtteil(stadtteil_id),
    street_id VARCHAR(128) REFERENCES core.street(street_id),
    address_text VARCHAR(512),
    house_no VARCHAR(20),
    postal_code VARCHAR(10),
    building_type VARCHAR(50) DEFAULT 'UNKNOWN' CHECK (building_type IN ('EFH', 'ZFH', 'MFH', 'GHD', 'UNKNOWN')),
    year_band_est VARCHAR(50),
    roof_type VARCHAR(50) DEFAULT 'UNKNOWN' CHECK (roof_type IN ('FLAT', 'PITCHED', 'COMPLEX', 'UNKNOWN')),
    is_target_candidate BOOLEAN DEFAULT TRUE,
    geom Geometry(Polygon, 4326),
    centroid Geometry(Point, 4326),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_building_centroid ON core.building USING GIST (centroid);
CREATE INDEX idx_building_geom ON core.building USING GIST (geom);
CREATE INDEX idx_building_street_id ON core.building (street_id);

-- ==========================================
-- FEATURE SCHEMA
-- ==========================================

-- Segment-Building Mapping (Decoupled from core to support versioned clustering)
CREATE TABLE feature.segment_building_map (
    segment_building_id SERIAL PRIMARY KEY,
    segment_id VARCHAR(128) REFERENCES core.street_segment(segment_id),
    building_id VARCHAR(128) REFERENCES core.building(building_id),
    data_version VARCHAR(128) REFERENCES audit.data_version_registry(data_version),
    mapped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (segment_id, building_id, data_version)
);
CREATE INDEX idx_seg_bldg_map_segment ON feature.segment_building_map (segment_id);
CREATE INDEX idx_seg_bldg_map_building ON feature.segment_building_map (building_id);
CREATE INDEX idx_seg_bldg_map_version ON feature.segment_building_map (data_version);

CREATE TABLE feature.building_feature (
    building_feature_id VARCHAR(128) PRIMARY KEY,
    building_id VARCHAR(128) REFERENCES core.building(building_id),
    data_version VARCHAR(128) REFERENCES audit.data_version_registry(data_version),
    
    -- Level A Parameters
    roof_area_est_m2 NUMERIC(10,2),
    roof_pv_kwp_est NUMERIC(6,2),
    roof_solar_score NUMERIC(5,2), 
    pv_existing_flag BOOLEAN DEFAULT FALSE,
    fernwaerme_flag BOOLEAN DEFAULT FALSE,
    district_heating_plan_flag BOOLEAN DEFAULT FALSE,
    
    -- Restrictions
    restriction_flag BOOLEAN DEFAULT FALSE,
    restriction_types VARCHAR(50)[], -- Array support for multiple restrictions e.g., '{"DENKMALSCHUTZ", "TREE_SHADING"}'
    
    -- Level A/B Proxies
    household_proxy numeric(4,1),
    owner_occ_proxy NUMERIC(5,2), -- Probability 0.0-1.0
    high_load_proxy NUMERIC(5,2),
    
    roi_base_score NUMERIC(5,2),
    confidence_score NUMERIC(5,2),
    source_coverage_score NUMERIC(5,2),
    
    -- Future-proofing for Level B/C models without DDL changes
    extended_attributes JSONB,
    
    feature_generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX uniq_bldg_feat_version ON feature.building_feature (building_id, data_version);
CREATE INDEX idx_bldg_feat_version ON feature.building_feature (data_version);

CREATE TABLE feature.segment_feature (
    segment_feature_id VARCHAR(128) PRIMARY KEY,
    segment_id VARCHAR(128) REFERENCES core.street_segment(segment_id),
    data_version VARCHAR(128) REFERENCES audit.data_version_registry(data_version),
    
    building_count INTEGER NOT NULL,
    target_building_count INTEGER NOT NULL,
    
    pv_saturation_ratio NUMERIC(5,4),
    fernwaerme_ratio NUMERIC(5,4),
    restriction_ratio NUMERIC(5,4),
    
    median_roof_area_est_m2 NUMERIC(10,2),
    median_roof_pv_kwp_est NUMERIC(6,2),
    dominant_building_type VARCHAR(50),
    dominant_year_band VARCHAR(50),
    
    homogeneity_score NUMERIC(5,4),
    eligibility_score NUMERIC(5,4),
    marketing_priority_score NUMERIC(5,4),
    confidence_index NUMERIC(5,4),
    
    aggregation_method VARCHAR(100),
    feature_generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX uniq_seg_feat_version ON feature.segment_feature (segment_id, data_version);
CREATE INDEX idx_seg_feat_version ON feature.segment_feature (data_version);

-- ==========================================
-- OUTPUT SCHEMA
-- ==========================================

CREATE TABLE output.segment_roi_profile (
    segment_roi_profile_id VARCHAR(128) PRIMARY KEY,
    segment_id VARCHAR(128) REFERENCES core.street_segment(segment_id),
    data_version VARCHAR(128) REFERENCES audit.data_version_registry(data_version),
    policy_version VARCHAR(50) NOT NULL,
    roi_engine_version VARCHAR(50) NOT NULL,
    scenario_name VARCHAR(100),
    
    typical_kwp NUMERIC(6,2),
    typical_annual_generation_kwh NUMERIC(10,2),
    typical_self_consumption_ratio NUMERIC(5,4),
    typical_year1_benefit_eur NUMERIC(10,2),
    typical_payback_years NUMERIC(5,2),
    typical_20y_profit_eur NUMERIC(12,2),
    co2_reduction_annual_kg NUMERIC(10,2),
    
    profile_confidence_index NUMERIC(5,4),
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE output.campaign_batch (
    campaign_batch_id VARCHAR(128) PRIMARY KEY,
    city_id VARCHAR(128) REFERENCES core.city(city_id),
    stadtteil_id VARCHAR(128) REFERENCES core.stadtteil(stadtteil_id),
    batch_name VARCHAR(255) NOT NULL,
    batch_status VARCHAR(50) DEFAULT 'DRAFT' CHECK (batch_status IN ('DRAFT', 'APPROVED', 'SENT_TO_PRINT', 'COMPLETED', 'CANCELLED')),
    campaign_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE TABLE output.flyer_payload (
    flyer_payload_id VARCHAR(128) PRIMARY KEY,
    segment_id VARCHAR(128) REFERENCES core.street_segment(segment_id),
    segment_roi_profile_id VARCHAR(128) REFERENCES output.segment_roi_profile(segment_roi_profile_id),
    campaign_batch_id VARCHAR(128) REFERENCES output.campaign_batch(campaign_batch_id),
    
    campaign_version VARCHAR(50),
    headline_de TEXT,
    subheadline_de TEXT,
    body_short_de TEXT,
    body_long_de TEXT,
    cta_de TEXT,
    
    target_household_est INTEGER,
    print_qty INTEGER,
    drop_priority INTEGER, 
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
