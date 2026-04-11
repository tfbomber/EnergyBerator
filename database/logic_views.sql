-- ==========================================
-- D-ESS Neuss GIS Aggregation & Logic Views
-- ==========================================

-- 1. Building Feature Aggregate Base
-- This view performs the heavy lifting of raw building-to-segment math.
CREATE OR REPLACE VIEW feature.v_segment_aggregation_base AS
WITH building_stats AS (
    SELECT 
        m.segment_id,
        m.data_version,
        bf.building_id,
        bf.roof_area_est_m2,
        bf.roof_pv_kwp_est,
        bf.pv_existing_flag,
        bf.fernwaerme_flag,
        bf.restriction_flag,
        b.building_type,
        b.year_band_est,
        bf.household_proxy
    FROM feature.segment_building_map m
    JOIN core.building b ON m.building_id = b.building_id
    JOIN feature.building_feature bf ON b.building_id = bf.building_id AND m.data_version = bf.data_version
),
counts AS (
    SELECT 
        segment_id,
        data_version,
        COUNT(*) as total_buildings,
        SUM(CASE WHEN pv_existing_flag THEN 1 ELSE 0 END) as count_pv_existing,
        SUM(CASE WHEN fernwaerme_flag THEN 1 ELSE 0 END) as count_fernwaerme,
        SUM(CASE WHEN restriction_flag THEN 1 ELSE 0 END) as count_restricted,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY roof_area_est_m2) as median_roof_area,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY roof_pv_kwp_est) as median_roof_pv_kwp,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY household_proxy) as median_household_size,
        STDDEV(roof_area_est_m2) as stddev_roof_area,
        STDDEV(household_proxy) as stddev_heating_proxy -- Placeholder for heating homogeneity
    FROM building_stats
    GROUP BY segment_id, data_version
),
dominant_types AS (
    -- Find the building type with the highest count per segment
    SELECT DISTINCT ON (segment_id, data_version)
        segment_id,
        data_version,
        building_type as mode_building_type,
        COUNT(*) OVER (PARTITION BY segment_id, data_version, building_type) as type_count
    FROM building_stats
    ORDER BY segment_id, data_version, type_count DESC
),
dominant_years AS (
    -- Find the year band with the highest count per segment
    SELECT DISTINCT ON (segment_id, data_version)
        segment_id,
        data_version,
        year_band_est as mode_year_band,
        COUNT(*) OVER (PARTITION BY segment_id, data_version, year_band_est) as year_count
    FROM building_stats
    ORDER BY segment_id, data_version, year_count DESC
)
SELECT 
    c.segment_id,
    c.data_version,
    c.total_buildings,
    c.median_roof_area,
    c.median_roof_pv_kwp,
    c.median_household_size,
    (c.count_pv_existing::NUMERIC / c.total_buildings) as pv_saturation_ratio,
    (c.count_fernwaerme::NUMERIC / c.total_buildings) as fernwaerme_ratio,
    (c.count_restricted::NUMERIC / c.total_buildings) as restriction_ratio,
    
    -- Modes with 60% Threshold Logic
    CASE 
        WHEN (dt.type_count::NUMERIC / c.total_buildings) >= 0.6 THEN dt.mode_building_type 
        ELSE NULL 
    END as dominant_building_type,
    
    CASE 
        WHEN (dy.year_count::NUMERIC / c.total_buildings) >= 0.6 THEN dy.mode_year_band 
        ELSE NULL 
    END as dominant_year_band,

    -- Homogeneity Logic
    1.0 / (1.0 + COALESCE(c.stddev_roof_area / NULLIF(c.median_roof_area, 0), 0)) as pv_homogeneity_score,
    1.0 / (1.0 + COALESCE(c.stddev_heating_proxy / NULLIF(c.median_household_size, 0), 0)) as heating_homogeneity_score

FROM counts c
JOIN dominant_types dt ON c.segment_id = dt.segment_id AND c.data_version = dt.data_version
JOIN dominant_years dy ON c.segment_id = dy.segment_id AND c.data_version = dy.data_version;


-- 2. Segment Qualification View
-- Implements the business logic for state assignment
CREATE OR REPLACE VIEW feature.v_segment_qualification AS
SELECT 
    segment_id,
    data_version,
    total_buildings,
    pv_homogeneity_score,
    heating_homogeneity_score,
    CASE 
        WHEN fernwaerme_ratio > 0.40 THEN 'BLOCKED'
        WHEN restriction_ratio > 0.30 THEN 'BLOCKED'
        WHEN total_buildings < 3 THEN 'BLOCKED' -- Too small for segment marketing
        WHEN pv_homogeneity_score < 0.60 OR dominant_building_type IS NULL THEN 'SPLIT_RECOMMENDED'
        WHEN heating_homogeneity_score < 0.50 THEN 'ELIGIBLE_WITH_CAUTION'
        WHEN dominant_building_type = 'MFH' THEN 'ELIGIBLE_WITH_CAUTION'
        ELSE 'ELIGIBLE'
    END as qualification_state,
    CASE
        WHEN fernwaerme_ratio > 0.40 THEN 'High district heating expansion'
        WHEN restriction_ratio > 0.30 THEN 'High restriction density (Heritage/Shading)'
        WHEN total_buildings < 3 THEN 'Too few target buildings in segment'
        WHEN pv_homogeneity_score < 0.60 THEN 'Low PV physical homogeneity'
        WHEN dominant_building_type IS NULL THEN 'No clear dominant building type (>60%)'
        ELSE NULL
    END as state_reason
FROM feature.v_segment_aggregation_base;


-- 3. ROI Input Payload Generator
-- Formats the aggregates into ScoredDataPoint JSON objects for the ROI engine
CREATE OR REPLACE VIEW output.v_segment_roi_payload_json AS
WITH base AS (
    SELECT 
        a.*,
        q.qualification_state
    FROM feature.v_segment_aggregation_base a
    JOIN feature.v_segment_qualification q ON a.segment_id = q.segment_id AND a.data_version = q.data_version
)
SELECT 
    segment_id,
    data_version,
    dominant_building_type as target_audience,
    qualification_state,
    jsonb_build_object(
        'kwp_override', jsonb_build_object(
            'value', median_roof_pv_kwp,
            'tier', 'PROXY_INFERRED',
            'source_tracker', 'LANUV_Median_Agg_Level_A'
        ),
        'household_size', jsonb_build_object(
            -- Map median numeric size to the string keys expected by e_base_table 
            'value', CASE 
                WHEN median_household_size <= 1.5 THEN '1'
                WHEN median_household_size <= 2.5 THEN '2'
                WHEN median_household_size <= 3.5 THEN '3'
                WHEN median_household_size <= 4.5 THEN '4'
                ELSE '5+'
            END,
            'tier', 'PROXY_INFERRED',
            'source_tracker', 'ZENSUS_HH_Size_Proxy_Level_B'
        ),
        'has_heat_pump', jsonb_build_object(
            'value', (fernwaerme_ratio <= 0.2), -- If district heating is low, assume HP potential
            'tier', 'PROXY_INFERRED',
            'source_tracker', 'STADTWERKE_Plan_Level_A_Inversion'
        ),
        'hp_bucket', jsonb_build_object(
            'value', CASE 
                WHEN dominant_year_band IN ('BEFORE_1919', '1919_1948', '1949_1978') THEN 'HIGH'
                ELSE 'MDM'
            END,
            'tier', 'PROXY_INFERRED',
            'source_tracker', 'ZENSUS_Age_Dominant_Level_B'
        ),
        'hp_input_mode', 'MODE_B',
        'scenario_mode', 'CONSERVATIVE_FLYER'
    ) as roi_inputs_payload
FROM base
WHERE qualification_state IN ('ELIGIBLE', 'ELIGIBLE_WITH_CAUTION');
