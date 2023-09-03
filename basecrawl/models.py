import datetime
import os

from dateutil.relativedelta import *
from django.contrib.auth.models import User
from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.conf import settings
from nameparser import HumanName

from rosetta import utils

class Player(BaseModel):
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)
    name = models.CharField(max_length=255)
    raw_name = models.CharField(max_length=255, blank=True, null=True)

    position = models.CharField(max_length=255, blank=True, null=True)
    simple_position = models.CharField(max_length=255, blank=True, null=True)

    birthdate = models.DateField(blank=True, null=True)
    birthdate_qa = models.BooleanField(default=False)
    raw_age = models.IntegerField(default=None, blank=True, null=True)

    bats = models.CharField(max_length=3, blank=True, null=True)
    throws = models.CharField(max_length=3, blank=True, null=True)
    height = models.CharField(max_length=15, blank=True, null=True)
    weight = models.CharField(max_length=3, blank=True, null=True)

    organization = models.CharField(max_length=255, blank=True, null=True)

    # IDs
    mlb_id = models.CharField(max_length=255, primary_key=True)
    scoresheet_id = models.CharField(max_length=255, blank=True, null=True)
    fg_id = models.CharField(max_length=255, blank=True, null=True)
    bp_id = models.CharField(max_length=255, blank=True, null=True)
    bref_id = models.CharField(max_length=255, blank=True, null=True)

    # Roster status
    roster_status = models.CharField(max_length=255, blank=True, null=True) # what does roster resource say about you?
    fypd_year = models.IntegerField(blank=True, null=True) # what year, if not pro, are you eligible to be a pro?
    is_pro = models.BooleanField(default=False) # are you in the mlb / milb?
    is_active = models.BooleanField(default=False) # are you an active or retired player?
    is_injured = models.BooleanField(default=False) # are you injured in some way?
    injured_list = models.CharField(max_length=255, blank=True, null=True) # what list are you on?
    is_mlb = models.BooleanField(default=False) # are you currently in the mlb?
    level = models.CharField(max_length=255, blank=True, null=True) # what level are you?

    # STATS
    # Here's the schema for a stats dictionary
    # required keys: year, level, type, timestamp
    # YEAR — the season these stats accrued in, or "career"
    # LEVEL - the levels these stats cover, e.g., A/AA or AA/AAA or MLB
    # TYPE — the type of stats, e.g., majors, minors
    # note: we combine all minor league stats in a single record
    # but we do not combine major leage WITH minor league.
    # this is because major league stats are used for the game
    # but minor / other pro league stats are not.
    # TIMESTAMP - a UNIX timestamp of when this record was created
    #
    # Any actual stats keys are fine following these.
    # Pitching and hitting stats can be in the same dictionary.
    #
    stats = models.JSONField(null=True, blank=True)

    class Meta():
        ordering = ['last_name', 'first_name']

    def __unicode__(self):
        return f"{self.name}"

    @property
    def mlb_image_url(self):
        return f"https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_213,q_auto:best/v1/people/{self.mlb_id}/headshot/67/current"

    @property
    def age(self):
        if self.birthdate:
            now = datetime.datetime.utcnow().date()
            return relativedelta(now, self.birthdate).years
        elif self.raw_age:
            return self.raw_age
        return None

    @property
    def mlb_url(self):
        if self.mlb_id:
            return f"https://www.mlb.com/player/{self.mlb_id}/"
        return None

    @property
    def mlb_api_url(self):
        if self.mlb_id:
            return f"https://statsapi.mlb.com/api/v1/people/{self.mlb_id}"
        return None

    @property
    def fg_url(self):
        if self.fg_id:
            return f"https://www.fangraphs.com/statss.aspx?playerid={self.fg_id}"
        return None

    def update_mlb_info(self):
        r = requests.get(self.mlb_api_url + "?hydrate=currentTeam,team")
        results = r.json().get('people', None)
        if results:
            if len(results) == 1:
                person = results[0]
                self.active = utils.to_bool(person['active'])

                if self.active:
                    self.first_name = person['firstName']
                    self.last_name = person['lastName']
                    self.birthdate = person['birthDate']

                    self.position = person['primaryPosition']['abbreviation']

                    try:
                        self.mlb_org = person['currentTeam']['abbreviation']
                    except KeyError:
                        pass
        
                    self.height = person['height']
                    self.weight = person['weight']
                    self.bats = person['batSide']['code']

                    try:
                        self.throws = person['pitchHand']['code']
                    except KeyError:
                        print(person)


    def set_simple_position(self):
        if self.position:
            if self.position.upper() in ["P", "SP", "RP", "LHP", "RHP", "SR"]:
                self.simple_position = "P"

            if self.position.upper() in ["IF", "1B", "2B", "3B", "SS"]:
                self.simple_position = "IF"

            if self.position.upper() in ["OF", "CF", "LF", "RF"]:
                self.simple_position = "OF"

            if "/" in self.position:
                self.simple_position = "UT"

            if self.position.upper() in ["C", "CA"]:
                self.simple_position = "C"

            if self.position.upper() == "UT":
                self.simple_position = "UT"

    def set_name(self):
        if not self.name and not self.first_name and not self.last_name:
            if self.raw_name:
                self.name = self.raw_name

        if self.first_name and self.last_name:
            name_string = "%s" % self.first_name
            name_string += " %s" % self.last_name
            self.name = name_string

        if self.name:
            if not self.first_name and not self.last_name:
                n = HumanName(self.name)
                self.first_name = n.first
                if n.middle:
                    self.first_name = n.first + " " + n.middle
                self.last_name = n.last
                if n.suffix:
                    self.last_name = n.last + " " + n.suffix


    def save(self, *args, **kwargs):
        self.set_name()
        self.set_simple_position()

        super().save(*args, **kwargs)