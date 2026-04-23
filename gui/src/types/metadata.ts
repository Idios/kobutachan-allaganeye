export type MatchType = 'fl_match' | 'unknown';

export type TypeOverride = MatchType | 'skip';

export interface DetectionParams {
  sample_interval: number;
  blackout_threshold: number;
  min_match_duration: number;
  min_blackout_duration: number;
  no_audio: boolean;
  use_gpu: number | boolean | null;
  workers: number | null;
}

export interface Match {
  index: number;
  start_time: number;
  end_time: number;
  start_display: string;
  end_display: string;
  duration: number;
  duration_display: string;
  type: MatchType;
  output_file: string;
  name?: string;
  type_override?: TypeOverride;
  edited?: { start_time: number; end_time: number };
}

export interface Gap {
  start_time: number;
  end_time: number;
  start_display: string;
  end_display: string;
  duration: number;
  duration_display: string;
}

export interface Metadata {
  /**
   * #515: schema revision declaration. Optional on the TS type because
   * pre-0.2.0 files don't carry the field; readers treat missing as v1.
   * New writes always emit `"1"`.
   */
  schema_version?: '1';
  source: string;
  source_duration: number;
  source_duration_display: string;
  detected_at: string;
  detection_params: DetectionParams;
  matches: Match[];
  gaps: Gap[];
}
