from collections import defaultdict
import datetime

import lxml
import lxml.etree
import pytz
import requests
from legistar.events import LegistarAPIEventScraper
from pupa.scrape import Event, Scraper


class PittsburghEventsScraper(LegistarAPIEventScraper, Scraper) :
    BASE_URL = "http://webapi.legistar.com/v1/pittsburgh"
    WEB_URL = "http://pittsburgh.legistar.com/"
    EVENTSPAGE = "http://pittsburgh.legistar.com/Calendar.aspx"
    TIMEZONE = "America/New_York"

    def _event_key(self, event, web_scraper):

        # Overrides method from LegistarAPIEventScraper.
        # The package looks for event["Name"]["label"],
        # however in Pittsburgh"s case there"s no "label".

        response = web_scraper.get(event["iCalendar"]["url"], verify=False)
        event_time = web_scraper.ical(response.text).subcomponents[0]["DTSTART"].dt
        event_time = pytz.timezone(self.TIMEZONE).localize(event_time)

        key = (event["Meeting Name"],
               event_time)

        return key

    def clean_agenda_item_title(self, item_title):
      if "PUBLIC COMMENTS" in item_title:
        item_title = "PUBLIC COMMENTS"

      if item_title.endswith(':'):
        item_title = item_title[:-1]

      return item_title

    def get_meeting_video_link(self, link):
        # parse the redirect URL to extract the meeting id used for the video on pittsburgh.granicus.com
        id = link.split('ID1=')[1].split('&')[0]
        return "http://pittsburgh.granicus.com/player/clip/{}".format(id)


    def get_item_video_link(self, link):
        # parse the redirect URL to extract the meeting id + item id used for the video on pittsburgh.granicus.com
        meeting_id = link.split('ID1=')[1].split('&')[0]
        item_id = link.split('ID2=')[1].split('&')[0]
        return "http://pittsburgh.granicus.com/player/clip/{}?view_id=2&meta_id={}".format(meeting_id, item_id)


    def scrape(self, window=3):
        n_days_ago = datetime.datetime.utcnow() - datetime.timedelta(float(window))
        for api_event, event in self.events(n_days_ago):

            description = api_event["EventComment"]
            when = api_event["start"]
            location = api_event["EventLocation"]

            if location == "Council Chambers":
                location = "Council Chambers, 5th Floor, City-County Building, " \
                            "414 Grant Street, Pittsburgh, PA 15219"

            if not location :
                continue

            status_string = api_event["status"]

            if len(status_string) > 1 and status_string[1] :
                status_text = status_string[1].lower()
                if any(phrase in status_text
                       for phrase in ("rescheduled to",
                                      "postponed to",
                                      "reconvened to",
                                      "rescheduled to",
                                      "meeting recessed",
                                      "recessed meeting",
                                      "postponed to",
                                      "recessed until",
                                      "deferred",
                                      "time change",
                                      "date change",
                                      "recessed meeting - reconvene",
                                      "cancelled",
                                      "new date and time",
                                      "rescheduled indefinitely",
                                      "rescheduled for",)) :
                    status = "cancelled"
                elif status_text in ("rescheduled", "recessed") :
                    status = "cancelled"
                elif status_text in ("meeting reconvened",
                                     "reconvened meeting",
                                     "recessed meeting",
                                     "reconvene meeting",
                                     "rescheduled hearing",
                                     "rescheduled meeting",) :
                    status = api_event["status"]
                elif status_text in ("amended notice of meeting",
                                     "room change",
                                     "amended notice",
                                     "change of location",
                                     "revised - meeting date and time") :
                    status = api_event["status"]
                elif "room" in status_text :
                    location = status_string[1] + ", " + location
                elif status_text in ("wrong meeting date",) :
                    continue
                else :
                    print(status_text)
                    status = api_event["status"]
            else :
                status = api_event["status"]

            if event["Meeting Name"] == "Post Agenda":
                event_name = "Agenda Announcement"
            elif event["Meeting Name"] == "City Council":
                event_name = "Regular meeting"
            else:
                event_name = event["Meeting Name"]

            if description :
                e = Event(name=event_name,
                          start_date=when,
                          description=description,
                          location_name=location,
                          status=status)
            else :
                e = Event(name=event_name,
                          start_date=when,
                          location_name=location,
                          status=status)

            e.pupa_id = str(api_event["EventId"])

            if event["Meeting video"] != "Not\xa0available":
                if "url" not in event["Meeting video"]:
                    pass
                else:
                    video_url = self.get_meeting_video_link(event["Meeting video"]["url"])
                    e.add_media_link(note="Recording",
                                     url=video_url,
                                     type="recording",
                                     media_type="text/html")

            self.addDocs(e, event, "Published agenda")
            self.addDocs(e, event, "Published minutes")

            participant = event["Meeting Name"]

            if participant == "City Council" or participant == "Post Agenda":
                participant = "Pittsburgh City Council"

            e.add_participant(name=participant,
                              type="organization")

            for item in self.agenda(api_event):
                clean_title = self.clean_agenda_item_title(item["EventItemTitle"])
                agenda_item = e.add_agenda_item(clean_title)
                if item["EventItemMatterFile"]:
                    identifier = item["EventItemMatterFile"]
                    agenda_item.add_bill(identifier)
                if item["EventItemVideo"]:
                    item_video_url = self.get_meeting_video_link(event["Meeting video"]["url"]) + \
                                     '?view_id=2&meta_id=' + str(item["EventItemVideo"])
                    agenda_item.add_media_link(note="Recording",
                                               url=item_video_url,
                                               type="recording",
                                               media_type="text/html")



            participants = set()

            for call in self.rollcalls(api_event):
                if call["RollCallValueName"] == "Present":
                    participants.add(call["RollCallPersonName"])

            for person in participants:
                e.add_participant(name=person,
                                  type="person")

            e.add_source(self.BASE_URL + "/events/{EventId}".format(**api_event),
                         note="api")

            try:
                detail_url = event["Meeting Details"]["url"]
            except TypeError:
                e.add_source(self.EVENTSPAGE, note="web")
            else:
                if requests.head(detail_url).status_code == 200:
                    e.add_source(detail_url, note="web")

            yield e
