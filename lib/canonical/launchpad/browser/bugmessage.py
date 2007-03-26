# Copyright 2004-2007 Canonical Ltd.  All rights reserved.

"""IBugMessage-related browser view classes."""

__metaclass__ = type
__all__ = [
    'BugMessageAddFormView',
    'BugMessageAddSubFormView',
    ]

from StringIO import StringIO

from zope.formlib import form
from zope.schema import ValidationError

from canonical.launchpad.interfaces import IBugMessageAddForm
from canonical.launchpad.webapp import action, canonical_url
from canonical.launchpad.webapp import LaunchpadFormView


class BugMessageAddFormView(LaunchpadFormView):
    """Browser view class for adding a bug comment/attachment."""

    schema = IBugMessageAddForm

    @property
    def initial_values(self):
        return dict(subject=self.context.bug.followup_subject())

    @property
    def next_url(self):
        """Redirect to the bug's main page."""
        return canonical_url(self.context)

    def validate(self, data):
        comment = data.get('comment', None)
        filecontent = data.get('filecontent', None)
        if not comment and not filecontent:
            self.addError("Either a comment or attachment must be present")
    
    @action(u"Save Changes", name='save')
    def save_action(self, action, data):
        """Add the comment and/or attachment."""
        
        bug = self.context.bug

        # subscribe to this bug if the checkbox exists and was selected
        if 'email_me' in data and data['email_me']:
            bug.subscribe(self.user)

        # XXX: Write proper FileUpload field and widget instead of this
        # hack. -- Bjorn Tillenius, 2005-06-16
        file_ = self.request.form.get('field.filecontent')

        message = None
        if data['comment'] or file_:
            message = bug.newMessage(subject=data['subject'],
                                     content=data['comment'],
                                     owner=self.user)

            # A blank comment with only a subect line is always added
            # when the user attaches a file, so show the add comment
            # feedback message only when the user actually added a
            # comment.
            if data['comment']:
                self.request.response.addNotification(
                    "Thank you for your comment.")

        if file_:

            # Slashes in filenames cause problems, convert them to dashes
            # instead.
            filename = file_.filename.replace('/', '-')

            # if no description was given use the converted filename
            file_description = None
            if 'attachment_description' in data:
                file_description = data['attachment_description']
            if not file_description:
                file_description = filename

            # Process the attachment.
            bug.addAttachment(
                owner=self.user, file_=StringIO(data['filecontent']),
                filename=filename, description=file_description,
                comment=message, is_patch=data['patch'])

            self.request.response.addNotification(
                "Attachment %(filename)s added to bug.", filename=filename)

    def shouldShowEmailMeWidget(self):
        """Should the subscribe checkbox be shown?"""
        return not self.context.bug.isSubscribed(self.user)

    def collapsedState(self):
        """Should the comment/attachment form be collapsed or expanded?"""
        collapsed_state = "expanded"
        return collapsed_state

    def shouldShowLegend(self):
        """Should the legend for the enclosing fieldset be shown?"""
        return False
    


class BugMessageAddSubFormView(BugMessageAddFormView):
    """Browser view class for adding a bug comment/attachment.
       This view is used when the form is contained at the bottom of
       the index page. 
    """

    def collapsedState(self):
        """Should the comment/attachment form be collapsed or expanded?"""
        if self.errors:
            collapsed_state = "expanded"
        else:
            collapsed_state = "collapsed"
        return collapsed_state

    def shouldShowLegend(self):
        """Should the legend for the enclosing fieldset be shown?"""
        return True
    
