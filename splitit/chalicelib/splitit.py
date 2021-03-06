import collections
import logging
import re

from chalicelib.model import Check, Location, LineItem

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

LocationTaxAndTip = collections.namedtuple('LocationTaxAndTip', ['tax_multiplier', 'tip_multiplier'])


class ConflictError(Exception):
    pass


def _validate_item_exists(item, type, item_id):
    if not item:
        raise KeyError('%s %s does not exist' % (type, item_id))


def get_check(check_id):
    try:
        return Check.get(check_id)
    except Check.DoesNotExist:
        return None


def _validate_date(date):
    if not date or not _DATE_RE.match(date):
        raise ValueError('Invalid date: %s' % date)


def put_check(date, description):
    _validate_date(date)

    if not description:
        raise ValueError('Invalid description: %s' % description)

    check = Check()
    check.date = date
    check.description = description

    put_location(check, save=False)

    check.save()

    return check


def update_check(check, date, description):
    modified = False

    if date:
        _validate_date(date)
        check.date = date
        modified = True

    if description:
        check.description = description
        modified = True

    if modified:
        check.save()

    return check


def remove_check(check_id):
    check = get_check(check_id)

    if check:
        check.delete()

    return check


def _validate_tax_in_cents(tax_in_cents):
    if tax_in_cents and (type(tax_in_cents) != int or tax_in_cents < 0):
        raise ValueError('Invalid tax: %s' % str(tax_in_cents))


def _validate_tip_in_cents(tip_in_cents):
    if tip_in_cents and (type(tip_in_cents) != int or tip_in_cents < 0):
        raise ValueError('Invalid tip: %s' % str(tip_in_cents))


def put_location(check, location_name=None, tax_in_cents=None, tip_in_cents=None, save=True):
    _validate_tax_in_cents(tax_in_cents)
    _validate_tip_in_cents(tip_in_cents)

    for location in check.locations:
        if location.name == location_name:
            raise ValueError('A location with the name %s already exists' % location_name)

    location = Location()
    location.name = location_name

    if tax_in_cents:
        location.tax_in_cents = tax_in_cents

    if tip_in_cents:
        location.tip_in_cents = tip_in_cents

    check.locations.append(location)

    if save:
        check.save()

    return location


def update_location(check, location_id, name=None, tax_in_cents=None, tip_in_cents=None):
    _validate_tax_in_cents(tax_in_cents)
    _validate_tip_in_cents(tip_in_cents)

    location = None

    modified = False
    for loc in check.locations:
        if loc.location_id == location_id:
            if name:
                modified = True
                loc.name = name

            if tax_in_cents is not None:
                modified = True
                loc.tax_in_cents = tax_in_cents

            if tip_in_cents is not None:
                modified = True
                loc.tip_in_cents = tip_in_cents

            location = loc
            break

    if not location:
        return None

    if modified:
        check.save()

    return location


def delete_location(check, location_id):
    location = None

    locations = []
    for loc in check.locations:
        if loc.location_id == location_id:
            location = loc
            continue
        locations.append(loc)

    if not location:
        return None

    if location.line_item_count != 0:
        raise ValueError('Cannot remove location with line items')

    if not locations:
        raise ValueError('Cannot remove all locations from check: %s' % check.check_id)

    check.locations = locations
    check.save()

    return location


def _validate_amount_in_cents(amount_in_cents):
    if amount_in_cents is not None and (type(amount_in_cents) != int or amount_in_cents < 0):
        raise ValueError('Invalid amount: %s' % str(amount_in_cents))


def _validate_owners(owners, expected_owner_count=None):
    if owners:
        if expected_owner_count is None:
            expected_owner_count = len(owners)

        if expected_owner_count != len(set(owners)):
            raise ValueError('Duplicate owners in: %s' % ', '.join(owners))


def _get_location(check, location_id):
    if not location_id:
        if len(check.locations) == 1:
            return check.locations[0]

        else:
            for location in check.locations:
                if not location.name:
                    return location
    else:
        for location in check.locations:
            if location.location_id == location_id:
                return location

    return None


def put_line_item(check, name, location_id=None, owners=None, amount_in_cents=None, save_check=True):
    if not name:
        raise ValueError('Missing name')

    location = _get_location(check, location_id)
    _validate_item_exists(location, 'Location', location_id)

    _validate_amount_in_cents(amount_in_cents)
    _validate_owners(owners)

    line_item = LineItem()
    line_item.name = name
    line_item.check_id = check.check_id
    line_item.location_id = location.location_id

    if amount_in_cents is not None:
        line_item.amount_in_cents = amount_in_cents

    if owners:
        line_item.owners.extend(owners)

    check.line_item_ids.append(line_item.line_item_id)

    location.line_item_count += 1

    line_item.save()

    if save_check:
        check.save()

    return line_item


def _validate_line_item_in_check(check, line_item_id):
    if line_item_id not in check.line_item_ids:
        _validate_item_exists(None, 'Line Item', line_item_id)


def _get_line_item(line_item_id):
    try:
        return LineItem.get(line_item_id)
    except LineItem.DoesNotExist:
        return None


def _remove_line_item_from_location(check, line_item):
    location = _get_location(check, line_item.location_id)
    location.line_item_count -= 1


def update_line_item(check, line_item_id, name=None, location_id=None, owners_to_add=None, owners_to_remove=None,
                     amount_in_cents=None):

    _validate_line_item_in_check(check, line_item_id)

    line_item = _get_line_item(line_item_id)
    _validate_item_exists(line_item, 'Line Item', line_item_id)

    modified = False
    modified_check = False

    if name:
        line_item.name = name
        modified = True

    if location_id:
        new_location = _get_location(check, location_id)
        _validate_item_exists(new_location, 'Location', location_id)

        _remove_line_item_from_location(check, line_item)

        new_location.line_item_count += 1
        line_item.location_id = location_id

        modified = True
        modified_check = True

    if owners_to_add:
        orig_owner_ct = len(line_item.owners)
        line_item.owners.extend(owners_to_add)
        _validate_owners(line_item.owners, orig_owner_ct + len(owners_to_add))

        modified = True

    if owners_to_remove:
        line_item.owners = [o for o in line_item.owners if o not in owners_to_remove]

        modified = True

    if amount_in_cents is not None:
        _validate_amount_in_cents(amount_in_cents)
        line_item.amount_in_cents = amount_in_cents
        modified = True

    if modified:
        line_item.save()

    if modified_check:
        check.save()

    return line_item


def delete_line_item(check, line_item_id):
    line_item = _get_line_item(line_item_id)
    if not line_item:
        return None

    if line_item_id in check.line_item_ids:
        _remove_line_item_from_location(check, line_item)
        check.save()

    line_item.delete()

    return line_item


def summarize_check(check):
    line_items = list(LineItem.batch_get(check.line_item_ids))

    locations_by_id = {}
    location_tax_and_tip_by_id = {}

    for location in check.locations:
        locations_by_id[location.location_id] = location

        loc_total = 0

        for line_item in line_items:
            if location.location_id == line_item.location_id:
                loc_total += line_item.amount_in_cents

        tax_multiplier = float(location.tax_in_cents) / loc_total if loc_total else 0
        tip_multiplier = float(location.tip_in_cents) / loc_total if loc_total else 0

        location_tax_and_tip_by_id[location.location_id] = LocationTaxAndTip(tax_multiplier, tip_multiplier)

        logging.debug('Location "%s" (%s), total=%d, tax multiplier=%.2f, tip multiplier=%.2f',
                      location.name, location.location_id, loc_total, tax_multiplier, tip_multiplier)

    by_owner = collections.Counter()

    for line_item in line_items:
        location = locations_by_id[line_item.location_id]
        location_tax_and_tip = location_tax_and_tip_by_id[line_item.location_id]

        for owner in line_item.owners:
            adjusted_amount = int(round((1 + location_tax_and_tip.tax_multiplier + location_tax_and_tip.tip_multiplier)
                                        * (line_item.amount_in_cents / len(line_item.owners))))
            by_owner[owner] += adjusted_amount

    return {
        'description': check.description,
        'date': check.date,
        'locations': [location.name for location in check.locations],
        'amountInCentsByOwner': by_owner,
    }
