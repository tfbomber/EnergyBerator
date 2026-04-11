from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Any

class DataAcquisitionTier(str, Enum):
    LEVEL_A = "DIRECT_TRUTH"      # Direct objective data (ALKIS, MaStR, Cadastre)
    LEVEL_B = "PROXY_INFERRED"    # Algorithmic/Proxy-based inference (Age + Footprint -> HP potential)
    LEVEL_C = "MANUAL_REQUIRED"   # Highly subjective/Individual (Actual consumption, exact ownership)

class ScoredDataPoint(BaseModel):
    value: Optional[Any] = Field(None, description="The actual data value")
    tier: DataAcquisitionTier
    source_tracker: str = Field(..., description="Audit trail: Where did this come from or how was it inferred?")
    is_user_overridden: bool = Field(False, description="True if a human verified or overrode this value")

    def resolve(self, fallback=None):
        """
        [ZERO_INFERENCE] Implementation:
        If the value is missing and it's Level C, we return the fallback 
        but we should have triggered a signal before this if it's strictly required.
        """
        if self.value is None:
            return fallback
        return self.value

class HouseholdAssessmentData(BaseModel):
    case_id: str
    
    # Level A: Ground Truth
    building_footprint_sqm: Optional[ScoredDataPoint] = None
    district_heating_zone: Optional[ScoredDataPoint] = None
    rooftop_potential_kwp: Optional[ScoredDataPoint] = None
    
    # Level B: Inferred Proxies
    inferred_heat_pump_potential: Optional[ScoredDataPoint] = None
    inferred_purchasing_power_tier: Optional[ScoredDataPoint] = None
    
    # Level C: Individual Data
    actual_yearly_consumption_kwh: Optional[ScoredDataPoint] = None
    actual_hp_installed: Optional[ScoredDataPoint] = None
    actual_ev_installed: Optional[ScoredDataPoint] = None
