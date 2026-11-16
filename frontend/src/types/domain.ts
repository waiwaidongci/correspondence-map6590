export type User={id:number;email:string;name:string;role:string};
export type Study={id:number;name:string;filename:string;description:string;rows:number;columns:number;total:number};
export type Category={id:number;study_id:number;axis:string;code:string;label:string;position:number};
export type Cell={id:number;study_id:number;row_id:number;column_id:number;count:number};
export type Point={id:number;code:string;label:string;axis:string;mass:number;coordinates:number[];contributions:number[];cos2:(number|null)[];display_quality:number|null;chi_square_distance_squared:number;centroid:boolean};
export type CAResult={fingerprint:string;n:number;rank:number;total_inertia:number;direction_available:boolean;displayed_axes:number;retained_inertia:number|null;axes:{axis:number;singular_value:number;inertia:number;share:number}[];row_points:Point[];column_points:Point[];dropped_rows:Category[];dropped_columns:Category[];row_categories:Category[];column_categories:Category[];table:number[][];degenerate_axes:number[][];zero_message:string|null;diagnostics:{chi_square:number;df:number;p_value:number;expected:number[][];pearson_residuals:number[][];adjusted_standardized_residuals:number[][];expected_min:number;fraction_expected_under5:number;any_expected_under1:boolean;asymptotic_reliable:boolean;p_label:string}};
export type Run={id:number;study_id:number;name:string;axes:number;status:string;result:Partial<CAResult>;error?:string;created_at:string};
export type Note={id:number;run_id:number;name:string;category_ids:number[];interpretation:string;next_step:string;status:string;review_note:string;created_at:string};
export type Audit={id:number;actor:string;action:string;detail:object;created_at:string};

export type IntervalCategory={id:number;study_id:number;axis:string;code:string;label:string;position:number;verified_total:number};
export type IntervalBound={id:number;study_id:number;row_id:number;column_id:number;lower:number;upper:number};
export type IntervalStudy={id:number;name:string;filename:string;description:string;rows:number;columns:number;row_verified_total:number;column_verified_total:number;lower_total:number;upper_total:number};
export type IntervalConflict={code:string;title:string;detail:string;row?:number;column?:number;cut?:any};
export type IntervalBounds={value:number;lower_bound?:number;upper_bound?:number;proved:boolean;table:number[][]|null;mode?:string};
export type IntervalResult={algorithm:string;dimensions:number[];n:number;time_limit:number;status:string;feasible:boolean;exact:boolean;effective_rows:number;effective_columns:number;proven_range:{min_lower_bound:number;min_feasible_value:number;max_feasible_value:number;max_upper_bound:number|null};min:IntervalBounds;max:IntervalBounds;conflicts?:IntervalConflict[];lower_matrix:number[][];upper_matrix:number[][];row_totals:number[];column_totals:number[];row_categories?:{id:number;code:string;label:string;verified_total:number}[];column_categories?:{id:number;code:string;label:string;verified_total:number}[];elapsed:number;timed_out?:boolean;notes?:string[];unit_segments?:boolean};
export type IntervalRun={id:number;study_id:number;name:string;time_limit:number;status:string;result:Partial<IntervalResult>;error?:string;created_at:string};
export type IntervalStudyDetail={id:number;name:string;filename:string;description:string;row_categories:IntervalCategory[];column_categories:IntervalCategory[];cells:{row_id:number;column_id:number;lower:number;upper:number}[];totals_consistent:boolean;input_conflicts:{code:string;title:string}[]};
