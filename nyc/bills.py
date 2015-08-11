from legistar.bills import LegistarBillScraper
from pupa.scrape import Bill, Vote
import datetime
from collections import defaultdict
import pytz

class NYCBillScraper(LegistarBillScraper):
    LEGISLATION_URL = 'http://legistar.council.nyc.gov/Legislation.aspx'
    BASE_URL = 'http://legistar.council.nyc.gov/'
    TIMEZONE = "US/Eastern"

    VOTE_OPTIONS = {'affirmative' : 'yes',
                    'absent' : 'absent',
                    'medical' : 'absent'}

    def sessions(self, action_date) :
        for session in (2014, 2010, 2006, 2002, 1996) :
            if action_date >= datetime.datetime(session, 1, 1, 
                                               tzinfo=pytz.timezone(self.TIMEZONE)) :
                return str(session)


    def scrape(self):

        for leg_summary in self.legislation(created_after=datetime.datetime(2015, 1, 1)) :
            leg_type = BILL_TYPES[leg_summary['Type']]

            bill = Bill(identifier=leg_summary['File\xa0#'],
                        title=leg_summary['Title'],
                        legislative_session=None,
                        classification=leg_type,
                        from_organization={"name":"New York City Council"})
            bill.add_source(leg_summary['url'])

            leg_details, history = self.details(leg_summary['url'])

            for sponsorship in self._sponsors(leg_details.get('Sponsors', [])) :
                sponsor, sponsorship_type, primary = sponsorship
                bill.add_sponsorship(sponsor, sponsorship_type,
                                     'person', primary)


            for i, attachment in enumerate(leg_details.get(u'Attachments', [])) :
                if i == 0 :
                    bill.add_version_link(attachment['label'],
                                          attachment['url'],
                                          media_type="application/pdf")
                else :
                    bill.add_document_link(attachment['label'],
                                           attachment['url'],
                                           media_type="application/pdf")

            earliest_action = min(self.toTime(action['Date']) 
                                  for action in history)

            bill.legislative_session = self.sessions(earliest_action)

            for action in history :
                action_description = action['Action']
                action_date = self.toDate(action['Date'])
                responsible_org = action['Action\xa0By']
                if responsible_org == 'City Council' :
                    responsible_org = 'New York City Council'
                act = bill.add_action(action_description,
                                      action_date,
                                      organization={'name': responsible_org},
                                      classification=None)

                if 'url' in action['Action\xa0Details'] :
                    action_detail_url = action['Action\xa0Details']['url']
                    result, votes = self.extractVotes(action_detail_url)
                    if votes :
                        action_vote = Vote(legislative_session=bill.legislative_session, 
                                           motion_text=action_description,
                                           organization={'name': responsible_org},
                                           classification=None,
                                           start_date=action_date,
                                           result=result,
                                           bill=bill)
                        action_vote.add_source(action_detail_url)

                        yield action_vote

            yield bill


    def _sponsors(self, sponsors) :
        for i, sponsor in enumerate(sponsors) :
            if i == 0 :
                primary = True
                sponsorship_type = "Primary"
            else :
                primary = False
                sponsorship_type = "Regular"
            
            sponsor_name = sponsor['label']
            if sponsor_name == '(in conjunction with the Mayor)' :
                sponsor_name = 'Mayor'

            yield sponsor_name, sponsorship_type, primary
                

BILL_TYPES = {'Introduction' : 'bill',
              'Resolution'   : 'resolution',
              'Land Use Application': None, 
              'Oversight': None, 
              'Land Use Call-Up': None, 
              'Communication': None, 
              "Mayor's Message": None, 
              'Tour': None, 
              'Petition': 'petition', 
              'SLR': None}

ACTION_CLASSIFICATION = {
    'Hearing on P-C Item by Comm' : None,
    'Approved by Committee with Modifications and Referred to CPC' : 'committee-passage',
    'Hearing Scheduled by Mayor' : None,
    'P-C Item Approved by Comm' : 'committee-passage',
    'Recessed' : None,
    'Amendment Proposed by Comm' : 'amendment-introduction',
    'P-C Item Laid Over by Comm' : 'deferred',
    'Approved by Subcommittee with Modifications and Referred to CPC' : 'committee-passage',
    'Re-referred to Committee by Council' : 'committee-referral',
    'Approved by Subcommittee' : 'committee-passage',
    'Amended by Committee' : 'amendment-passage',
    'Referred to Comm by Council' : 'committee-referral',
    'Sent to Mayor by Council' : None,
    'P-C Item Approved by Committee with Companion Resolution' : 'committee-passage',
    'Approved by Council' : 'passage',
    'Hearing Held by Mayor' : None,
    'Approved, by Council' : 'passage',
    'Introduced by Council' : 'introduction',
    'Approved by Committee with Companion Resolution' : 'committee-passage',
    'Rcvd, Ord, Prnt, Fld by Council' : None,
    'Laid Over by Subcommittee' : 'deferred',
    'Laid Over by Committee' : 'deferred',
    'Filed by Council' : 'filing',
    'Filed by Subcommittee' : 'filing',
    'Filed by Committee with Companion Resolution' : 'filing',
    'Hearing Held by Committee' : None,
    'Approved by Committee' : 'committee-referral',
    'Approved with Modifications and Referred to the City Planning Commission pursuant to Rule 11.70(b) of the Rules of the Council and Section 197-(d) of the New York City Charter.' : None,
    'Filed, by Committee' : 'filing',
    'Recved from Mayor by Council' : 'executive-received',
    'Signed Into Law by Mayor' : 'executive-signature',
    'Filed by Committee' : 'filing'
}

