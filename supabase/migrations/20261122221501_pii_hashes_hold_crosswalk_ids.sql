-- registry_state sha256: 5fdbb520f957f694447686b80b0161da4e95658da4c7e8cf053fe40614f2753e

CREATE OR REPLACE FUNCTION shared.pii_token_hashes() RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $fn$
    SELECT encode(sha256(convert_to(s.token, 'UTF8')), 'hex')
    FROM (
        SELECT regexp_split_to_table(lower(o.human_name), '[[:space:]]+') AS token FROM shared.owner o
        UNION
        SELECT lower(o.fantrax_username) FROM shared.owner o
        UNION
        SELECT c.discord_user_id FROM shared.owner_crosswalk c
    ) s
    WHERE s.token IS NOT NULL AND s.token <> ''
$fn$;
