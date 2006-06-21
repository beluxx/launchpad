SET client_min_messages=ERROR;

/* Set a default on the ShippingRequest.daterequested column */
ALTER TABLE ShippingRequest ALTER COLUMN daterequested
    SET DEFAULT CURRENT_TIMESTAMP AT TIME ZONE 'UTC';

/* We need to enforce a single outstanding request per recipient. We
can't maintain multi table constraints without race conditions, so we need
to duplicate the information that a shipment exists in the shippingrequest
table */

ALTER TABLE ShippingRequest ADD COLUMN shipped boolean NOT NULL DEFAULT FALSE;

UPDATE ShippingRequest SET shipped=TRUE WHERE id IN (
    SELECT request FROM shipment);

CREATE TRIGGER shipment_maintain_shipped_flag_t
BEFORE INSERT OR UPDATE OR DELETE ON Shipment
FOR EACH ROW EXECUTE PROCEDURE shipment_maintain_shipped_flag();

/* This should be NOT NULL */
ALTER TABLE Shipment ALTER COLUMN request SET NOT NULL;

/* Trash orders that will violate our constraint. We leave the first unshipped
duplicate order untouched. */
DELETE FROM RequestedCDs
USING ShippingRequest
WHERE
    RequestedCDs.request = ShippingRequest.id
    AND shipped IS FALSE
    AND approved IS NOT FALSE
    AND cancelled IS FALSE
    AND recipient IN (
        SELECT recipient FROM ShippingRequest
        WHERE
            shipped IS FALSE
            AND approved IS NOT FALSE
            AND cancelled IS FALSE
        GROUP BY recipient
        HAVING count(*) > 1
        )
    AND ShippingRequest.id NOT IN (
        SELECT min(id)
        FROM ShippingRequest
        WHERE
            shipped IS FALSE
            AND approved IS NOT FALSE
            AND cancelled IS FALSE
        GROUP BY recipient
        HAVING COUNT(*) > 1
        );

DELETE FROM ShippingRequest
WHERE
    shipped IS FALSE
    AND recipient IN (
        SELECT recipient FROM ShippingRequest
        WHERE
            shipped IS FALSE
            AND approved IS NOT FALSE
            AND cancelled IS FALSE
        GROUP BY recipient
        HAVING count(*) > 1
        )
    AND id NOT IN (
        SELECT min(id)
        FROM ShippingRequest
        WHERE
            shipped IS FALSE
            AND approved IS NOT FALSE
            AND cancelled IS FALSE
        GROUP BY recipient
        HAVING COUNT(*) > 1
        );

/* Now create the constraint. We do this using a stored procedure
   as we need to detect if we are running on production, or will be
   loading our sample data. This is because it is necessary for us to
   hard code the id of the shipit-admins team into the constraint.
 */
CREATE OR REPLACE FUNCTION create_the_index() RETURNS boolean AS $$
    rv = plpy.execute("SELECT id FROM Person WHERE name='shipit-admins'")
    try:
        shipit_admins_id = rv[0]["id"]
        assert shipit_admins_id == 243601, 'Unexpected shipit-admins id'
    except IndexError:
        shipit_admins_id = 54 # Value in sampledata
    sql = """
        CREATE UNIQUE INDEX shippingrequest_one_outstanding_request_unique
        ON ShippingRequest(recipient)
        WHERE
            shipped IS FALSE
            AND cancelled IS FALSE
            AND approved IS NOT FALSE
            AND recipient != %d
        """ % shipit_admins_id
    plpy.execute(sql)
    return True
$$ LANGUAGE plpythonu;

SELECT create_the_index();

DROP FUNCTION create_the_index();

-- These indexes are needed for people merge performance
CREATE INDEX product__security_contact__idx ON Product(security_contact)
    WHERE security_contact IS NOT NULL;
CREATE INDEX product__bugcontact__idx ON Product(bugcontact)
    WHERE bugcontact IS NOT NULL;
CREATE INDEX product__driver__idx ON Product(driver)
    WHERE driver IS NOT NULL;

INSERT INTO LaunchpadDatabaseRevision VALUES (40, 59, 0);

