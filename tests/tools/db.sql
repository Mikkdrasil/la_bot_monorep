DROP SCHEMA if exists public CASCADE;

CREATE SCHEMA public AUTHORIZATION <<CLOUD_POSTGRES_USERNAME>>;

-- DROP SEQUENCE change_log_id_seq;

CREATE SEQUENCE change_log_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE comments_id_seq;

CREATE SEQUENCE comments_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE communications_last_inline_msg_id_seq;

CREATE SEQUENCE communications_last_inline_msg_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE dialogs_id_seq;

CREATE SEQUENCE dialogs_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE dict_search_activities_id_seq;

CREATE SEQUENCE dict_search_activities_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE feedback_id_seq;

CREATE SEQUENCE feedback_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE forum_summary_snapshot_id_seq;

CREATE SEQUENCE forum_summary_snapshot_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE geocode_last_api_call_id_seq;

CREATE SEQUENCE geocode_last_api_call_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE geocode_rate_limit_id_seq;

CREATE SEQUENCE geocode_rate_limit_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE geocoding_id_seq;

CREATE SEQUENCE geocoding_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE msg_from_bot_id_seq;

CREATE SEQUENCE msg_from_bot_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE my_serial;

CREATE SEQUENCE my_serial
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE news_id_seq;

CREATE SEQUENCE news_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE notif_by_user_message_id_seq;

CREATE SEQUENCE notif_by_user_message_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE notif_by_user_status_id_seq;

CREATE SEQUENCE notif_by_user_status_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE notif_functions_registry_id_seq;

CREATE SEQUENCE notif_functions_registry_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE notif_mailing_status_id_seq;

CREATE SEQUENCE notif_mailing_status_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE notif_mailings_mailing_id_seq;

CREATE SEQUENCE notif_mailings_mailing_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE notif_stat_sending_speed_id_seq;

CREATE SEQUENCE notif_stat_sending_speed_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE parsed_snapshot_entry_id_seq;

CREATE SEQUENCE parsed_snapshot_entry_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE prev_snapshot_id_seq;

CREATE SEQUENCE prev_snapshot_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE regions_id_seq;

CREATE SEQUENCE regions_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE regions_to_folders_id_seq;

CREATE SEQUENCE regions_to_folders_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_activities_id_seq;

CREATE SEQUENCE search_activities_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_activities_id_seq1;

CREATE SEQUENCE search_activities_id_seq1
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_attributes_id_seq;

CREATE SEQUENCE search_attributes_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_events_id_seq;

CREATE SEQUENCE search_events_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_first_posts_id_seq;

CREATE SEQUENCE search_first_posts_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_health_check_id_seq;

CREATE SEQUENCE search_health_check_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_locations_id_seq;

CREATE SEQUENCE search_locations_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE search_places_id_seq;

CREATE SEQUENCE search_places_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE searches_id_seq;

CREATE SEQUENCE searches_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE stat_api_usage_actual_searches_id_seq;

CREATE SEQUENCE stat_api_usage_actual_searches_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE stat_map_usage_id_seq;

CREATE SEQUENCE stat_map_usage_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_attributes_id_seq;

CREATE SEQUENCE user_attributes_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_attributes_id_seq1;

CREATE SEQUENCE user_attributes_id_seq1
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_coordinates_id_seq;

CREATE SEQUENCE user_coordinates_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_onboarding_id_seq;

CREATE SEQUENCE user_onboarding_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_pref_age_id_seq;

CREATE SEQUENCE user_pref_age_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_pref_radius_id_seq;

CREATE SEQUENCE user_pref_radius_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_pref_region_id_seq;

CREATE SEQUENCE user_pref_region_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_pref_search_whitelist_id_seq;

CREATE SEQUENCE user_pref_search_whitelist_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_pref_topic_type_id_seq;

CREATE SEQUENCE user_pref_topic_type_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_pref_urgency_id_seq;

CREATE SEQUENCE user_pref_urgency_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_preferences_id_seq;

CREATE SEQUENCE user_preferences_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_regional_preferences_id_seq;

CREATE SEQUENCE user_regional_preferences_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_roles_id_seq;

CREATE SEQUENCE user_roles_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_stat_id_seq;

CREATE SEQUENCE user_stat_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE user_statuses_history_id_seq;

CREATE SEQUENCE user_statuses_history_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE users_id_seq;

CREATE SEQUENCE users_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;-- public."_old_search_event_stages" определение

-- Drop table

-- DROP TABLE "_old_search_event_stages";

CREATE TABLE "_old_search_event_stages" (
	id int4 NOT NULL,
	"type" varchar(20) NOT NULL,
	stage varchar(20) NOT NULL,
	CONSTRAINT search_event_stages_unique UNIQUE (id)
);


-- public.change_log определение

-- Drop table

-- DROP TABLE change_log;

CREATE TABLE change_log (
	id serial4 NOT NULL,
	parsed_time timestamp NULL,
	search_forum_num int4 NULL,
	changed_field varchar(255) NULL,
	new_value varchar NULL,
	notification_sent varchar(3) NULL,
	parameters varchar NULL,
	notif_sent_staging varchar(1) NULL,
	change_type int4 NULL,
	CONSTRAINT change_log_pkey PRIMARY KEY (id)
);


-- public."comments" определение

-- Drop table

-- DROP TABLE "comments";

CREATE TABLE "comments" (
	id serial4 NOT NULL,
	comment_url varchar NULL,
	comment_text varchar NULL,
	comment_author_nickname varchar NULL,
	comment_author_link varchar NULL,
	search_forum_num int4 NULL,
	comment_num int4 NULL,
	comment_global_num varchar(10) NULL,
	notification_sent varchar(1) NULL,
	notif_sent_staging varchar(1) NULL,
	notif_sent_inforg varchar(1) NULL,
	CONSTRAINT comments_pkey PRIMARY KEY (id)
);


-- public.communications_last_inline_msg определение

-- Drop table

-- DROP TABLE communications_last_inline_msg;

CREATE TABLE communications_last_inline_msg (
	id serial4 NOT NULL,
	user_id int8 NOT NULL,
	"timestamp" timestamptz NULL,
	message_id int8 NULL,
	CONSTRAINT communications_last_inline_msg_user_message UNIQUE (user_id, message_id)
);


-- public.dialogs определение

-- Drop table

-- DROP TABLE dialogs;

CREATE TABLE dialogs (
	id serial4 NOT NULL,
	"timestamp" timestamp NULL,
	user_id int8 NULL,
	author varchar(10) NULL,
	message_id int8 NULL,
	message_text varchar NULL,
	CONSTRAINT dialogs_pkey PRIMARY KEY (id)
);


-- public.dict_notif_types определение

-- Drop table

-- DROP TABLE dict_notif_types;

CREATE TABLE dict_notif_types (
	type_id int4 NOT NULL,
	type_name varchar(100) NOT NULL,
	CONSTRAINT notif_mailing_types_pkey PRIMARY KEY (type_id)
);


-- public.dict_search_activities определение

-- Drop table

-- DROP TABLE dict_search_activities;

CREATE TABLE dict_search_activities (
	id serial4 NOT NULL,
	activity_id varchar NULL,
	activity_name varchar NULL,
	CONSTRAINT dict_search_activities_pkey PRIMARY KEY (id)
);


-- public.dict_topic_types определение

-- Drop table

-- DROP TABLE dict_topic_types;

CREATE TABLE dict_topic_types (
	id int4 NOT NULL,
	topic_type_name varchar(20) NULL,
	CONSTRAINT dict_topic_types_pkey PRIMARY KEY (id)
);


-- public.feedback определение

-- Drop table

-- DROP TABLE feedback;

CREATE TABLE feedback (
	id serial4 NOT NULL,
	username varchar NULL,
	feedback_text varchar NULL,
	feedback_time timestamp NULL,
	user_id varchar NULL,
	message_id int4 NULL,
	CONSTRAINT feedback_pkey PRIMARY KEY (id)
);


-- public.forum_summary_snapshot определение

-- Drop table

-- DROP TABLE forum_summary_snapshot;

CREATE TABLE forum_summary_snapshot (
	search_forum_num int4 NULL,
	parsed_time timestamp NULL,
	status_short varchar NULL,
	forum_search_title varchar NULL,
	cut_link varchar NULL,
	search_start_time timestamp NULL,
	num_of_replies int4 NULL,
	family_name varchar NULL,
	age int4 NULL,
	id serial4 NOT NULL,
	forum_folder_id int4 NULL,
	topic_type varchar(30) NULL,
	display_name varchar(100) NULL,
	age_min int4 NULL,
	age_max int4 NULL,
	status varchar(20) NULL,
	locations varchar NULL,
	city_locations varchar NULL,
	topic_type_id int4 NULL,
	CONSTRAINT forum_summary_snapshot_pkey PRIMARY KEY (id)
);


-- public.functions_registry определение

-- Drop table

-- DROP TABLE functions_registry;

CREATE TABLE functions_registry (
	id serial4 NOT NULL,
	time_start timestamp NULL,
	time_finish timestamp NULL,
	event_id int8 NULL,
	cloud_function_name varchar(30) NULL,
	params json NULL,
	triggered_by int8 NULL,
	function_id int8 NULL,
	triggered_by_func_id int8 NULL,
	CONSTRAINT notif_functions_registry_pkey PRIMARY KEY (id)
);


-- public.geo_divisions определение

-- Drop table

-- DROP TABLE geo_divisions;

CREATE TABLE geo_divisions (
	division_id int4 NOT NULL,
	division_name varchar(40) NULL,
	CONSTRAINT geo_divisions_pkey PRIMARY KEY (division_id)
);


-- public.geo_folders определение

-- Drop table

-- DROP TABLE geo_folders;

CREATE TABLE geo_folders (
	folder_id int4 NOT NULL,
	division_id int4 NULL,
	folder_type varchar(12) NULL,
	folder_subtype varchar(26) NULL,
	CONSTRAINT geo_folders_pkey PRIMARY KEY (folder_id)
);


-- public.geo_regions определение

-- Drop table

-- DROP TABLE geo_regions;

CREATE TABLE geo_regions (
	region_id varchar(6) NOT NULL,
	division_id int4 NULL,
	polygon_id int4 NULL,
	name_full varchar(100) NULL,
	name_short varchar(30) NULL,
	federal_district varchar(17) NULL,
	CONSTRAINT geo_regions_pkey PRIMARY KEY (region_id)
);


-- public.geocode_last_api_call определение

-- Drop table

-- DROP TABLE geocode_last_api_call;

CREATE TABLE geocode_last_api_call (
	id serial4 NOT NULL,
	geocoder varchar(20) NULL,
	"timestamp" timestamptz NULL,
	CONSTRAINT geocode_last_api_call_pkey PRIMARY KEY (id)
);


-- public.geocode_rate_limit определение

-- Drop table

-- DROP TABLE geocode_rate_limit;

CREATE TABLE geocode_rate_limit (
	id serial4 NOT NULL,
	geocoder varchar(10) NULL,
	rate varchar(10) NULL,
	"period" timestamptz NULL,
	requests int4 NULL,
	CONSTRAINT geocode_rate_limit_pkey PRIMARY KEY (id)
);


-- public.geocoding определение

-- Drop table

-- DROP TABLE geocoding;

CREATE TABLE geocoding (
	id serial4 NOT NULL,
	address varchar NULL,
	status varchar NULL,
	latitude float8 NULL,
	longitude float8 NULL,
	geocoder varchar(10) NULL,
	"timestamp" timestamptz NULL,
	CONSTRAINT geocode_unique_address UNIQUE (address),
	CONSTRAINT geocoding_pkey PRIMARY KEY (id)
);


-- public.msg_from_bot определение

-- Drop table

-- DROP TABLE msg_from_bot;

CREATE TABLE msg_from_bot (
	id serial4 NOT NULL,
	"time" timestamp NULL,
	msg_type varchar NULL,
	msg_text varchar NULL,
	user_id int8 NULL,
	CONSTRAINT msg_from_bot_pkey PRIMARY KEY (id)
);


-- public.news определение

-- Drop table

-- DROP TABLE news;

CREATE TABLE news (
	id serial4 NOT NULL,
	stage varchar NULL,
	"text" varchar NULL,
	status varchar NULL,
	CONSTRAINT news_pkey PRIMARY KEY (id)
);


-- public.notif_by_user__archive определение

-- Drop table

-- DROP TABLE notif_by_user__archive;

CREATE TABLE notif_by_user__archive (
	message_id int8 NOT NULL,
	mailing_id int8 NULL,
	change_log_id int4 NULL,
	user_id int8 NULL,
	change_type int4 NULL,
	message_type varchar(6) NULL,
	created timestamp NULL,
	completed timestamp NULL,
	cancelled timestamp NULL,
	failed timestamp NULL,
	CONSTRAINT notif_by_user__archive_pkey PRIMARY KEY (message_id)
);


-- public.notif_by_user__history определение

-- Drop table

-- DROP TABLE notif_by_user__history;

CREATE TABLE notif_by_user__history (
	message_id int8 NULL,
	mailing_id int4 NULL,
	user_id int8 NULL,
	message_content varchar NULL,
	message_text varchar NULL,
	message_type varchar(50) NULL,
	message_params varchar NULL,
	message_group_id int4 NULL,
	change_log_id int4 NULL,
	created timestamp NULL,
	completed timestamp NULL,
	cancelled timestamp NULL,
	failed timestamp NULL,
	num_of_fails int4 NULL
);


-- public.notif_by_user_status определение

-- Drop table

-- DROP TABLE notif_by_user_status;

CREATE TABLE notif_by_user_status (
	id bigserial NOT NULL,
	message_id int8 NULL,
	"event" varchar(100) NOT NULL,
	event_timestamp timestamp NOT NULL,
	context varchar NULL,
	mailing_id int4 NULL,
	change_log_id int4 NULL,
	user_id int8 NULL,
	message_type varchar(50) NULL,
	CONSTRAINT notif_by_user_status_pkey PRIMARY KEY (id)
);


-- public.notif_by_user_status__history определение

-- Drop table

-- DROP TABLE notif_by_user_status__history;

CREATE TABLE notif_by_user_status__history (
	id int8 NULL,
	message_id int8 NULL,
	"event" varchar(100) NULL,
	event_timestamp timestamp NULL,
	context varchar NULL,
	mailing_id int4 NULL,
	change_log_id int4 NULL,
	user_id int8 NULL,
	message_type varchar(50) NULL
);


-- public.notif_stat_sending_speed определение

-- Drop table

-- DROP TABLE notif_stat_sending_speed;

CREATE TABLE notif_stat_sending_speed (
	id serial4 NOT NULL,
	"timestamp" timestamp NULL,
	num_of_msgs int4 NULL,
	speed float4 NULL,
	ttl_time float4 NULL,
	CONSTRAINT notif_stat_sending_speed_pkey PRIMARY KEY (id)
);


-- public.old_dict_regions определение

-- Drop table

-- DROP TABLE old_dict_regions;

CREATE TABLE old_dict_regions (
	id int4 DEFAULT nextval('my_serial'::regclass) NOT NULL,
	region_name varchar NULL
);


-- public.old_folders определение

-- Drop table

-- DROP TABLE old_folders;

CREATE TABLE old_folders (
	folder_id int4 NULL,
	folder_name varchar(255) NULL,
	folder_type varchar(100) NULL,
	region varchar(255) NULL,
	region_id int4 NULL
);


-- public.old_regions определение

-- Drop table

-- DROP TABLE old_regions;

CREATE TABLE old_regions (
	id int4 DEFAULT nextval('regions_id_seq'::regclass) NOT NULL,
	region_name varchar NULL,
	yandex_reg_id _int4 NULL,
	CONSTRAINT regions_pkey PRIMARY KEY (id)
);


-- public.old_regions_to_folders определение

-- Drop table

-- DROP TABLE old_regions_to_folders;

CREATE TABLE old_regions_to_folders (
	id int4 DEFAULT nextval('regions_to_folders_id_seq'::regclass) NOT NULL,
	forum_folder_id int4 NULL,
	region_id int4 NULL,
	folder_description varchar NULL,
	CONSTRAINT regions_to_folders_pkey PRIMARY KEY (id)
);


-- public.parsed_snapshot определение

-- Drop table

-- DROP TABLE parsed_snapshot;

CREATE TABLE parsed_snapshot (
	search_forum_num int4 NULL,
	parsed_time timestamp NULL,
	status_short varchar(255) NULL,
	forum_search_title varchar(255) NULL,
	cut_link varchar(255) NULL,
	search_start_time timestamp NULL,
	num_of_replies int4 NULL,
	entry_id serial4 NOT NULL,
	search_person_age int4 NULL,
	"name" varchar NULL,
	forum_folder_id int4 NULL,
	CONSTRAINT parsed_snapshot_pkey PRIMARY KEY (entry_id)
);


-- public.prev_snapshot определение

-- Drop table

-- DROP TABLE prev_snapshot;

CREATE TABLE prev_snapshot (
	hash varchar NULL,
	id serial4 NOT NULL,
	CONSTRAINT prev_snapshot_pkey PRIMARY KEY (id)
);


-- public.search_activities определение

-- Drop table

-- DROP TABLE search_activities;

CREATE TABLE search_activities (
	id serial4 NOT NULL,
	search_forum_num int4 NULL,
	activity_type varchar NULL,
	activity_parameters varchar NULL,
	activity_status varchar NULL,
	"timestamp" timestamp NULL,
	CONSTRAINT search_activities_pkey1 PRIMARY KEY (id)
);


-- public.search_attributes определение

-- Drop table

-- DROP TABLE search_attributes;

CREATE TABLE search_attributes (
	id serial4 NOT NULL,
	search_forum_num int4 NULL,
	attribute_name varchar NULL,
	attribute_value varchar NULL,
	"timestamp" timestamp NULL,
	CONSTRAINT search_attributes_pkey PRIMARY KEY (id)
);


-- public.search_coordinates определение

-- Drop table

-- DROP TABLE search_coordinates;

CREATE TABLE search_coordinates (
	id int4 DEFAULT nextval('search_activities_id_seq'::regclass) NOT NULL,
	search_id int4 NULL,
	activity_type varchar NULL,
	latitude varchar NULL,
	longitude varchar NULL,
	upd_time timestamp NULL,
	coord_type varchar NULL,
	CONSTRAINT search_activities_pkey PRIMARY KEY (id)
);


-- public.search_first_posts определение

-- Drop table

-- DROP TABLE search_first_posts;

CREATE TABLE search_first_posts (
	id serial4 NOT NULL,
	search_id int4 NULL,
	"timestamp" timestamp NULL,
	actual bool NULL,
	content_hash varchar NULL,
	"content" varchar NULL,
	num_of_checks int4 NULL,
	coords varchar NULL,
	field_trip varchar NULL,
	content_compact varchar NULL,
	CONSTRAINT search_first_posts_pkey PRIMARY KEY (id)
);


-- public.search_first_posts__history определение

-- Drop table

-- DROP TABLE search_first_posts__history;

CREATE TABLE search_first_posts__history (
	id int4 NOT NULL,
	search_id int4 NULL,
	"timestamp" timestamp NULL,
	actual bool NULL,
	content_hash varchar NULL,
	"content" varchar NULL,
	num_of_checks int4 NULL,
	coords varchar NULL,
	field_trip varchar NULL,
	content_compact varchar NULL
);


-- public.search_health_check определение

-- Drop table

-- DROP TABLE search_health_check;

CREATE TABLE search_health_check (
	id serial4 NOT NULL,
	search_forum_num int4 NULL,
	"timestamp" timestamp NULL,
	status varchar(50) NULL,
	CONSTRAINT search_health_check_pkey PRIMARY KEY (id)
);


-- public.search_locations определение

-- Drop table

-- DROP TABLE search_locations;

CREATE TABLE search_locations (
	id serial4 NOT NULL,
	search_id int8 NULL,
	address varchar(50) NULL,
	"timestamp" timestamp NULL,
	CONSTRAINT search_locations_pkey PRIMARY KEY (id)
);


-- public.search_places определение

-- Drop table

-- DROP TABLE search_places;

CREATE TABLE search_places (
	id serial4 NOT NULL,
	search_id int4 NULL,
	address varchar NULL,
	"timestamp" timestamp NULL,
	debug_title varchar NULL,
	CONSTRAINT search_places_pkey PRIMARY KEY (id)
);


-- public.searches определение

-- Drop table

-- DROP TABLE searches;

CREATE TABLE searches (
	search_forum_num int4 NULL,
	parsed_time timestamp NULL,
	status_short varchar(255) NULL,
	forum_search_title varchar(255) NULL,
	cut_link varchar(255) NULL,
	search_start_time timestamp NULL,
	num_of_replies int4 NULL,
	family_name varchar(255) NULL,
	age int4 NULL,
	id serial4 NOT NULL,
	forum_folder_id int4 NULL,
	topic_type varchar(30) NULL,
	display_name varchar(100) NULL,
	age_min int4 NULL,
	age_max int4 NULL,
	status varchar(20) NULL,
	city_locations varchar NULL,
	topic_type_id int4 NULL,
	CONSTRAINT searches_pkey PRIMARY KEY (id)
);


-- public.stat_api_usage_actual_searches определение

-- Drop table

-- DROP TABLE stat_api_usage_actual_searches;

CREATE TABLE stat_api_usage_actual_searches (
	id serial4 NOT NULL,
	"timestamp" timestamp NULL,
	request varchar NULL,
	response json NULL,
	CONSTRAINT stat_api_usage_actual_searches_pkey PRIMARY KEY (id)
);


-- public.stat_map_usage определение

-- Drop table

-- DROP TABLE stat_map_usage;

CREATE TABLE stat_map_usage (
	id serial4 NOT NULL,
	user_id int8 NULL,
	"timestamp" timestamp NULL,
	response json NULL,
	CONSTRAINT stat_map_usage_pkey PRIMARY KEY (id)
);


-- public.temp_my_devisions определение

-- Drop table

-- DROP TABLE temp_my_devisions;

CREATE TABLE temp_my_devisions (
	forum_folder_num int4 NULL,
	user_id int8 NULL
);


-- public.user_attributes определение

-- Drop table

-- DROP TABLE user_attributes;

CREATE TABLE user_attributes (
	id serial4 NOT NULL,
	forum_user_id int4 NULL,
	forum_username varchar NULL,
	callsign varchar NULL,
	region varchar NULL,
	auto_num varchar NULL,
	phone varchar NULL,
	"timestamp" timestamp NULL,
	firstname varchar NULL,
	lastname varchar NULL,
	user_id int8 NULL,
	CONSTRAINT user_attributes_pkey1 PRIMARY KEY (id)
);


-- public.user_coordinates определение

-- Drop table

-- DROP TABLE user_coordinates;

CREATE TABLE user_coordinates (
	id serial4 NOT NULL,
	latitude varchar NULL,
	longitude varchar NULL,
	upd_time timestamp NULL,
	user_id int8 NULL,
	CONSTRAINT user_coordinates_pkey PRIMARY KEY (id)
);


-- public.user_forum_attributes определение

-- Drop table

-- DROP TABLE user_forum_attributes;

CREATE TABLE user_forum_attributes (
	forum_user_id int4 NULL,
	forum_username varchar NULL,
	forum_age int4 NULL,
	forum_sex varchar NULL,
	forum_region varchar NULL,
	forum_auto_num varchar NULL,
	forum_callsign varchar NULL,
	forum_phone varchar NULL,
	forum_reg_date varchar NULL,
	status varchar NULL,
	"timestamp" timestamp NULL,
	id int4 DEFAULT nextval('user_attributes_id_seq'::regclass) NOT NULL,
	user_id int8 NULL,
	CONSTRAINT user_attributes_pkey PRIMARY KEY (id)
);


-- public.user_onboarding определение

-- Drop table

-- DROP TABLE user_onboarding;

CREATE TABLE user_onboarding (
	id serial4 NOT NULL,
	user_id int8 NULL,
	step_name varchar(15) NULL,
	"timestamp" timestamp NULL,
	step_id int4 NULL,
	CONSTRAINT user_onboarding_pkey PRIMARY KEY (id)
);


-- public.user_pref_age определение

-- Drop table

-- DROP TABLE user_pref_age;

CREATE TABLE user_pref_age (
	id serial4 NOT NULL,
	user_id int8 NULL,
	period_name varchar(30) NULL,
	period_set_date timestamp NULL,
	period_min int4 NULL,
	period_max int4 NULL,
	CONSTRAINT user_min_max UNIQUE (user_id, period_min, period_max),
	CONSTRAINT user_pref_age_pkey PRIMARY KEY (id)
);


-- public.user_pref_radius определение

-- Drop table

-- DROP TABLE user_pref_radius;

CREATE TABLE user_pref_radius (
	id serial4 NOT NULL,
	user_id int8 NULL,
	"type" varchar(10) NULL,
	radius int4 NULL,
	CONSTRAINT unique_user_id UNIQUE (user_id),
	CONSTRAINT user_pref_radius_pkey PRIMARY KEY (id)
);


-- public.user_pref_region определение

-- Drop table

-- DROP TABLE user_pref_region;

CREATE TABLE user_pref_region (
	id serial4 NOT NULL,
	user_id int8 NULL,
	region_id int4 NULL,
	"timestamp" timestamp NULL,
	CONSTRAINT user_pref_region_pkey PRIMARY KEY (id)
);


-- public.user_pref_search_filtering определение

-- Drop table

-- DROP TABLE user_pref_search_filtering;

CREATE TABLE user_pref_search_filtering (
	user_id int8 NOT NULL,
	filter_name _varchar NULL,
	filter_id int4 NULL,
	CONSTRAINT user_pref_search_filtering_user_id_key UNIQUE (user_id)
);


-- public.user_pref_topic_type определение

-- Drop table

-- DROP TABLE user_pref_topic_type;

CREATE TABLE user_pref_topic_type (
	id serial4 NOT NULL,
	user_id int8 NULL,
	"timestamp" timestamp NULL,
	topic_type_id int4 NULL,
	topic_type_name varchar(20) NULL,
	CONSTRAINT user_pref_topic_type_pkey PRIMARY KEY (id),
	CONSTRAINT user_topic_type UNIQUE (user_id, topic_type_id)
);


-- public.user_pref_urgency определение

-- Drop table

-- DROP TABLE user_pref_urgency;

CREATE TABLE user_pref_urgency (
	id serial4 NOT NULL,
	user_id int8 NULL,
	pref_id int4 NULL,
	pref_name varchar(15) NULL,
	"timestamp" timestamp NULL,
	CONSTRAINT user_pref_urgency_pkey PRIMARY KEY (id)
);


-- public.user_preferences определение

-- Drop table

-- DROP TABLE user_preferences;

CREATE TABLE user_preferences (
	id serial4 NOT NULL,
	preference varchar(255) NULL,
	user_id int8 NULL,
	pref_id int4 NULL,
	CONSTRAINT user_preferences_pkey PRIMARY KEY (id)
);
CREATE UNIQUE INDEX index_usr_prefs__user_id_and_pref_id ON public.user_preferences USING btree (user_id, pref_id);


-- public.user_regional_preferences определение

-- Drop table

-- DROP TABLE user_regional_preferences;

CREATE TABLE user_regional_preferences (
	id serial4 NOT NULL,
	forum_folder_num int4 NULL,
	user_id int8 NULL,
	CONSTRAINT user_regional_preferences_pkey PRIMARY KEY (id)
);


-- public.user_roles определение

-- Drop table

-- DROP TABLE user_roles;

CREATE TABLE user_roles (
	id serial4 NOT NULL,
	"role" varchar NULL,
	user_id int8 NULL,
	CONSTRAINT user_roles_pkey PRIMARY KEY (id)
);


-- public.user_stat определение

-- Drop table

-- DROP TABLE user_stat;

CREATE TABLE user_stat (
	id serial4 NOT NULL,
	num_of_new_search_notifs int4 NULL,
	user_id int8 NULL,
	CONSTRAINT tb_uq UNIQUE (user_id),
	CONSTRAINT user_stat_pkey PRIMARY KEY (id)
);


-- public.user_statuses_history определение

-- Drop table

-- DROP TABLE user_statuses_history;

CREATE TABLE user_statuses_history (
	id serial4 NOT NULL,
	status varchar NULL,
	"date" timestamp NULL,
	user_id int8 NULL,
	CONSTRAINT user_statuses_history_pkey PRIMARY KEY (id)
);
CREATE UNIQUE INDEX index_user_statuses_hist ON public.user_statuses_history USING btree (user_id, date);


-- public.users определение

-- Drop table

-- DROP TABLE users;

CREATE TABLE users (
	id serial4 NOT NULL,
	username_telegram varchar NULL,
	reg_date timestamp NULL,
	status varchar NULL,
	status_change_date timestamp NULL,
	user_id int8 NULL,
	"role" varchar(255) NULL,
	CONSTRAINT users_pkey PRIMARY KEY (id)
);
CREATE UNIQUE INDEX users_user_id ON public.users USING btree (user_id);


-- public.notif_mailings определение

-- Drop table

-- DROP TABLE notif_mailings;

CREATE TABLE notif_mailings (
	mailing_id serial4 NOT NULL,
	topic_id int4 NOT NULL,
	source_script varchar(200) NULL,
	mailing_type int4 NULL,
	change_log_id int4 NOT NULL,
	CONSTRAINT notif_mailings_pkey PRIMARY KEY (mailing_id),
	CONSTRAINT notif_mail_type FOREIGN KEY (mailing_type) REFERENCES dict_notif_types(type_id)
);


-- public.search_events определение

-- Drop table

-- DROP TABLE search_events;

CREATE TABLE search_events (
	id serial4 NOT NULL,
	search_id int4 NULL,
	"event" int4 NULL,
	event_timestamp timestamp NOT NULL,
	is_active bool NOT NULL,
	dubug_event_proof varchar NULL,
	CONSTRAINT search_events_pkey PRIMARY KEY (id),
	CONSTRAINT search_events_event FOREIGN KEY ("event") REFERENCES "_old_search_event_stages"(id)
);


-- public.user_pref_search_whitelist определение

-- Drop table

-- DROP TABLE user_pref_search_whitelist;

CREATE TABLE user_pref_search_whitelist (
	id serial4 NOT NULL,
	user_id int8 NULL,
	search_id int4 NULL,
	"timestamp" timestamp NULL,
	search_following_mode varchar(30) NULL,
	CONSTRAINT user_pref_search_whitelist_pkey PRIMARY KEY (id),
	CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);
CREATE UNIQUE INDEX idx_user_search_unique ON public.user_pref_search_whitelist USING btree (user_id, search_id);


-- public.notif_by_user определение

-- Drop table

-- DROP TABLE notif_by_user;

CREATE TABLE notif_by_user (
	message_id bigserial NOT NULL,
	mailing_id int4 NULL,
	user_id int8 NOT NULL,
	message_content varchar NULL,
	message_text varchar NULL,
	message_type varchar(50) NOT NULL,
	message_params varchar NULL,
	message_group_id int4 NULL,
	change_log_id int4 NULL,
	created timestamp NULL,
	completed timestamp NULL,
	cancelled timestamp NULL,
	failed timestamp NULL,
	num_of_fails int4 NULL,
	CONSTRAINT notif_by_user_pkey PRIMARY KEY (message_id),
	CONSTRAINT notif_by_user_mailing FOREIGN KEY (mailing_id) REFERENCES notif_mailings(mailing_id)
);


-- public.notif_mailing_status определение

-- Drop table

-- DROP TABLE notif_mailing_status;

CREATE TABLE notif_mailing_status (
	id serial4 NOT NULL,
	mailing_id int4 NULL,
	"event" varchar(100) NULL,
	event_timestamp timestamp NULL,
	CONSTRAINT notif_mailing_status_pkey PRIMARY KEY (id),
	CONSTRAINT notif_mail_status FOREIGN KEY (mailing_id) REFERENCES notif_mailings(mailing_id)
);


-- public.geo_folders_view исходный текст

CREATE OR REPLACE VIEW geo_folders_view
AS WITH stage_0 AS (
         SELECT f.folder_id,
            f.division_id,
            f.folder_type,
            f.folder_subtype,
            d.division_name
           FROM geo_folders f
             LEFT JOIN geo_divisions d ON d.division_id = f.division_id
        )
 SELECT stage_0.folder_id,
    stage_0.division_id,
    stage_0.division_name,
    stage_0.folder_type,
    stage_0.folder_subtype,
        CASE
            WHEN stage_0.folder_subtype::text = 'searches all'::text THEN stage_0.division_name
            WHEN stage_0.folder_subtype::text = 'searches active'::text THEN (stage_0.division_name::text || ' – Активные поиски'::text)::character varying
            WHEN stage_0.folder_subtype::text = 'searches info support'::text THEN (stage_0.division_name::text || ' – Инфо поддержка'::text)::character varying
            WHEN stage_0.folder_subtype::text = 'searches finished'::text THEN (stage_0.division_name::text || ' – Завершенные поиски'::text)::character varying
            WHEN stage_0.folder_type::text = 'events'::text THEN (stage_0.division_name::text || ' – Мероприятия'::text)::character varying
            ELSE NULL::character varying
        END AS folder_display_name
   FROM stage_0
  ORDER BY stage_0.folder_id;


-- public.user_view исходный текст

CREATE OR REPLACE VIEW user_view
AS WITH reg_and_status AS (
         SELECT users.user_id,
            users.reg_date,
                CASE
                    WHEN users.reg_date < '2023-05-14 12:40:00'::timestamp without time zone THEN 'before'::text
                    ELSE 'after'::text
                END AS reg_period,
                CASE
                    WHEN users.status IS NULL OR users.status::text = 'unblocked'::text THEN 'act'::text
                    ELSE 'deact'::text
                END AS act_status
           FROM users
        ), notif_setting AS (
         SELECT DISTINCT user_preferences.user_id,
            'yes'::text AS notif_setting
           FROM user_preferences
          WHERE user_preferences.pref_id <> 20
        ), reg_setting AS (
         SELECT DISTINCT user_regional_preferences.user_id,
            'yes'::text AS folder_setting
           FROM user_regional_preferences
        ), summary_receipt AS (
         SELECT DISTINCT dialogs.user_id,
            'yes'::text AS receives_summaries
           FROM dialogs
          WHERE dialogs.message_text::text ~~ 'Последние 20%'::text OR dialogs.message_text::text ~~ 'Актуальные поиски за%'::text OR dialogs.message_text::text ~~ 'В разделе <a href=%'::text
        ), onboard_step AS (
         SELECT user_onboarding.user_id,
            max(user_onboarding.step_id) AS onb_step
           FROM user_onboarding
          GROUP BY user_onboarding.user_id
        ), last_user_msg AS (
         SELECT DISTINCT ON (d.user_id) d.user_id,
            d."timestamp",
            "substring"(d.message_text::text, 1, 50) AS last_msg,
                CASE
                    WHEN d.message_text::text = '/start'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_start,
                CASE
                    WHEN d.message_text::text = 'я состою в ЛизаАлерт'::text OR d.message_text::text = 'я хочу помогать ЛизаАлерт'::text OR d.message_text::text = 'я ищу человека'::text OR d.message_text::text = 'не хочу говорить'::text OR d.message_text::text = 'у меня другая задача'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_role,
                CASE
                    WHEN d.message_text::text = 'нет, я из другого региона'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_moscow,
                CASE
                    WHEN d.message_text::text = 'да, Москва – мой регион'::text OR r.id IS NOT NULL THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_reg
           FROM dialogs d
             LEFT JOIN old_dict_regions r ON d.message_text::text = r.region_name::text
          WHERE d.author::text = 'user'::text
          ORDER BY d.user_id, d."timestamp" DESC
        )
 SELECT u.user_id,
    r_n_s.reg_date,
    r_n_s.reg_period,
    r_n_s.act_status,
    ns.notif_setting,
    rs.folder_setting,
    sr.receives_summaries,
    o.onb_step,
    l_u_m.last_msg,
    l_u_m.last_msg_start,
    l_u_m.last_msg_role,
    l_u_m.last_msg_moscow,
    l_u_m.last_msg_reg
   FROM users u
     LEFT JOIN reg_and_status r_n_s ON u.user_id = r_n_s.user_id
     LEFT JOIN notif_setting ns ON u.user_id = ns.user_id
     LEFT JOIN reg_setting rs ON u.user_id = rs.user_id
     LEFT JOIN summary_receipt sr ON u.user_id = sr.user_id
     LEFT JOIN onboard_step o ON u.user_id = o.user_id
     LEFT JOIN last_user_msg l_u_m ON u.user_id = l_u_m.user_id;


-- public.user_view_21 исходный текст

CREATE OR REPLACE VIEW user_view_21
AS WITH reg_setting AS (
         SELECT DISTINCT user_regional_preferences.user_id,
            'yes'::text AS folder_setting
           FROM user_regional_preferences
        ), onboard_step AS (
         SELECT user_onboarding.user_id,
            max(user_onboarding.step_id) AS onb_step
           FROM user_onboarding
          GROUP BY user_onboarding.user_id
        ), last_user_msg AS (
         SELECT DISTINCT ON (d.user_id) d.user_id,
            d."timestamp",
            "substring"(d.message_text::text, 1, 50) AS last_msg,
                CASE
                    WHEN d.message_text::text = '/start'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_start,
                CASE
                    WHEN d.message_text::text = 'я состою в ЛизаАлерт'::text OR d.message_text::text = 'я хочу помогать ЛизаАлерт'::text OR d.message_text::text = 'я ищу человека'::text OR d.message_text::text = 'не хочу говорить'::text OR d.message_text::text = 'у меня другая задача'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_role,
                CASE
                    WHEN d.message_text::text = 'нет, я из другого региона'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_moscow,
                CASE
                    WHEN d.message_text::text = 'да, Москва – мой регион'::text OR r.id IS NOT NULL THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_reg
           FROM dialogs d
             LEFT JOIN old_dict_regions r ON d.message_text::text = r.region_name::text
          WHERE d.author::text = 'user'::text
          ORDER BY d.user_id, d."timestamp" DESC
        )
 SELECT u.user_id,
    rs.folder_setting,
    o.onb_step,
    l_u_m.last_msg,
    l_u_m.last_msg_start,
    l_u_m.last_msg_role,
    l_u_m.last_msg_moscow,
    l_u_m.last_msg_reg
   FROM users u
     LEFT JOIN reg_setting rs ON u.user_id = rs.user_id
     LEFT JOIN onboard_step o ON u.user_id = o.user_id
     LEFT JOIN last_user_msg l_u_m ON u.user_id = l_u_m.user_id
  WHERE u.reg_date < '2023-05-14 12:40:00'::timestamp without time zone;


-- public.user_view_21_new исходный текст

CREATE OR REPLACE VIEW user_view_21_new
AS WITH reg_setting AS (
         SELECT DISTINCT user_regional_preferences.user_id,
            'yes'::text AS folder_setting
           FROM user_regional_preferences
        ), onboard_step AS (
         SELECT user_onboarding.user_id,
            max(user_onboarding.step_id) AS onb_step
           FROM user_onboarding
          GROUP BY user_onboarding.user_id
        ), last_user_msg AS (
         SELECT DISTINCT ON (d.user_id) d.user_id,
            d."timestamp",
            "substring"(d.message_text::text, 1, 50) AS last_msg,
                CASE
                    WHEN d.message_text::text = '/start'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_start,
                CASE
                    WHEN d.message_text::text = 'я состою в ЛизаАлерт'::text OR d.message_text::text = 'я хочу помогать ЛизаАлерт'::text OR d.message_text::text = 'я ищу человека'::text OR d.message_text::text = 'не хочу говорить'::text OR d.message_text::text = 'у меня другая задача'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_role,
                CASE
                    WHEN d.message_text::text = 'нет, я из другого региона'::text THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_moscow,
                CASE
                    WHEN d.message_text::text = 'да, Москва – мой регион'::text OR r.id IS NOT NULL THEN 'yes'::text
                    ELSE 'no'::text
                END AS last_msg_reg
           FROM dialogs d
             LEFT JOIN old_dict_regions r ON d.message_text::text = r.region_name::text
          WHERE d.author::text = 'user'::text
          ORDER BY d.user_id, d."timestamp" DESC
        )
 SELECT u.user_id,
    rs.folder_setting,
    o.onb_step,
    l_u_m.last_msg_reg
   FROM users u
     LEFT JOIN reg_setting rs ON u.user_id = rs.user_id
     LEFT JOIN onboard_step o ON u.user_id = o.user_id
     LEFT JOIN last_user_msg l_u_m ON u.user_id = l_u_m.user_id
  WHERE u.reg_date < '2023-05-14 12:40:00'::timestamp without time zone AND l_u_m.last_msg_reg = 'yes'::text AND o.onb_step IS NULL;


-- public.user_view_80 исходный текст

CREATE OR REPLACE VIEW user_view_80
AS WITH notif_setting AS (
         SELECT DISTINCT user_preferences.user_id,
            'yes'::text AS notif_setting
           FROM user_preferences
          WHERE user_preferences.pref_id <> 20
        ), summary_receipt AS (
         SELECT DISTINCT dialogs.user_id,
            'yes'::text AS receives_summaries
           FROM dialogs
          WHERE dialogs.message_text::text ~~ 'Последние 20%'::text OR dialogs.message_text::text ~~ 'Актуальные поиски за%'::text OR dialogs.message_text::text ~~ 'В разделе <a href=%'::text
        ), onboard_step AS (
         SELECT user_onboarding.user_id,
            max(user_onboarding.step_id) AS onb_step
           FROM user_onboarding
          GROUP BY user_onboarding.user_id
        )
 SELECT u.user_id,
    ns.notif_setting,
    sr.receives_summaries,
    o.onb_step
   FROM users u
     LEFT JOIN notif_setting ns ON u.user_id = ns.user_id
     LEFT JOIN summary_receipt sr ON u.user_id = sr.user_id
     LEFT JOIN onboard_step o ON u.user_id = o.user_id
  WHERE u.reg_date < '2023-05-14 12:40:00'::timestamp without time zone;


-- public.user_view_80_wo_last_msg исходный текст

CREATE OR REPLACE VIEW user_view_80_wo_last_msg
AS WITH notif_setting AS (
         SELECT DISTINCT user_preferences.user_id,
            'yes'::text AS notif_setting
           FROM user_preferences
          WHERE user_preferences.pref_id <> 20
        ), reg_setting AS (
         SELECT DISTINCT user_regional_preferences.user_id,
            'yes'::text AS folder_setting
           FROM user_regional_preferences
        ), onboard_step AS (
         SELECT user_onboarding.user_id,
            max(user_onboarding.step_id) AS onb_step
           FROM user_onboarding
          GROUP BY user_onboarding.user_id
        ), last_user_msg AS (
         SELECT DISTINCT ON (dialogs.user_id) dialogs.user_id,
            dialogs."timestamp",
            "substring"(dialogs.message_text::text, 1, 50) AS last_msg
           FROM dialogs
          WHERE dialogs.author::text = 'user'::text
          ORDER BY dialogs.user_id, dialogs."timestamp" DESC
        )
 SELECT u.user_id,
    ns.notif_setting,
    rs.folder_setting,
    o.onb_step,
    l_u_m.last_msg
   FROM users u
     LEFT JOIN notif_setting ns ON u.user_id = ns.user_id
     LEFT JOIN reg_setting rs ON u.user_id = rs.user_id
     LEFT JOIN onboard_step o ON u.user_id = o.user_id
     LEFT JOIN last_user_msg l_u_m ON u.user_id = l_u_m.user_id
  WHERE u.reg_date < '2023-05-14 12:40:00'::timestamp without time zone AND o.onb_step IS NULL AND ns.notif_setting = 'yes'::text AND rs.folder_setting = 'yes'::text AND l_u_m.last_msg IS NULL;



-- DROP FUNCTION public.generate_create_table_statement(varchar);

CREATE OR REPLACE FUNCTION public.generate_create_table_statement(p_table_name character varying)
 RETURNS SETOF text
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_table_ddl   text;
    column_record record;
    table_rec record;
    constraint_rec record;
    firstrec boolean;
BEGIN
    FOR table_rec IN
        SELECT c.relname FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE relkind = 'r'
                AND relname~ ('^('||p_table_name||')$')
                AND n.nspname <> 'pg_catalog'
                AND n.nspname <> 'information_schema'
                AND n.nspname !~ '^pg_toast'
                AND pg_catalog.pg_table_is_visible(c.oid)
          ORDER BY c.relname
    LOOP

        FOR column_record IN 
            SELECT 
                b.nspname as schema_name,
                b.relname as table_name,
                a.attname as column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) as column_type,
                CASE WHEN 
                    (SELECT substring(pg_catalog.pg_get_expr(d.adbin, d.adrelid) for 128)
                     FROM pg_catalog.pg_attrdef d
                     WHERE d.adrelid = a.attrelid AND d.adnum = a.attnum AND a.atthasdef) IS NOT NULL THEN
                    'DEFAULT '|| (SELECT substring(pg_catalog.pg_get_expr(d.adbin, d.adrelid) for 128)
                                  FROM pg_catalog.pg_attrdef d
                                  WHERE d.adrelid = a.attrelid AND d.adnum = a.attnum AND a.atthasdef)
                ELSE
                    ''
                END as column_default_value,
                CASE WHEN a.attnotnull = true THEN 
                    'NOT NULL'
                ELSE
                    'NULL'
                END as column_not_null,
                a.attnum as attnum,
                e.max_attnum as max_attnum
            FROM 
                pg_catalog.pg_attribute a
                INNER JOIN 
                 (SELECT c.oid,
                    n.nspname,
                    c.relname
                  FROM pg_catalog.pg_class c
                       LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                  WHERE c.relname = table_rec.relname
                    AND pg_catalog.pg_table_is_visible(c.oid)
                  ORDER BY 2, 3) b
                ON a.attrelid = b.oid
                INNER JOIN 
                 (SELECT 
                      a.attrelid,
                      max(a.attnum) as max_attnum
                  FROM pg_catalog.pg_attribute a
                  WHERE a.attnum > 0 
                    AND NOT a.attisdropped
                  GROUP BY a.attrelid) e
                ON a.attrelid=e.attrelid
            WHERE a.attnum > 0 
              AND NOT a.attisdropped
            ORDER BY a.attnum
        LOOP
            IF column_record.attnum = 1 THEN
                v_table_ddl:='CREATE TABLE '||column_record.schema_name||'.'||column_record.table_name||' (';
            ELSE
                v_table_ddl:=v_table_ddl||',';
            END IF;

            IF column_record.attnum <= column_record.max_attnum THEN
                v_table_ddl:=v_table_ddl||chr(10)||
                         '    '||column_record.column_name||' '||column_record.column_type||' '||column_record.column_default_value||' '||column_record.column_not_null;
            END IF;
        END LOOP;

        firstrec := TRUE;
        FOR constraint_rec IN
            SELECT conname, pg_get_constraintdef(c.oid) as constrainddef 
                FROM pg_constraint c 
                    WHERE conrelid=(
                        SELECT attrelid FROM pg_attribute
                        WHERE attrelid = (
                            SELECT oid FROM pg_class WHERE relname = table_rec.relname
                        ) AND attname='tableoid'
                    )
        LOOP
            v_table_ddl:=v_table_ddl||','||chr(10);
            v_table_ddl:=v_table_ddl||'CONSTRAINT '||constraint_rec.conname;
            v_table_ddl:=v_table_ddl||chr(10)||'    '||constraint_rec.constrainddef;
            firstrec := FALSE;
        END LOOP;
        v_table_ddl:=v_table_ddl||');';
        RETURN NEXT v_table_ddl;
    END LOOP;
END;
$function$
;