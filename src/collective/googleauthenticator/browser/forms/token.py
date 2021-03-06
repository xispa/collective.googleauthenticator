"""
Token validation.
"""

import logging

from zope.schema import TextLine
from zope.i18nmessageid import MessageFactory

from z3c.form import button, field

from plone.directives import form
from plone import api
from plone.z3cform.layout import wrap_form

from Products.statusmessages.interfaces import IStatusMessage

from collective.googleauthenticator.helpers import validate_token, validate_user_data, extract_request_data

logger = logging.getLogger('collective.googleauthenticator')

DEBUG = False

_ = MessageFactory('collective.googleauthenticator')

class ITokenForm(form.Schema):
    """
    Interface for the Google Authenticator Token validation form.
    """
    token = TextLine(
        title=_('Enter code'),
        description=_('Enter the verification code generated by your mobile application.'),
        required=True)


class TokenForm(form.SchemaForm):
    """
    Form for the Google Authenticator Token validation. Any user that has two-step verification enabled,
    uses this form upon logging in.
    """
    fields = field.Fields(ITokenForm)
    ignoreContext = True
    schema = ITokenForm
    label = _(u'Two-step verification')
    description = _(u'Confirm your login by entering the verification generated '
                    u'by the Google Authenticator app.')

    def action(self):
        return "{0}?{1}".format(
            self.request.getURL(),
            self.request.get('QUERY_STRING', '')
            )

    @button.buttonAndHandler(_('Verify'))
    def handleSubmit(self, action):
        """
        Here we should check couple of things:

        - If the token provided is valid.
        - If the signature contains the user data needed (username and hash made of his data are valid).

        If all is well and valid, we sudo login the user given.
        """

        data, errors = self.extractData()
        if errors:
            return False

        token = data.get('token', '')

        user = None
        username = self.request.get('auth_user', '')

        if username:
            user = api.user.get(username=username)

            # Validating the signed request data. If invalid (likely throttled with or expired), generate an
            # appropriate error message.
            user_data_validation_result = validate_user_data(request=self.request, user=user)
            if not user_data_validation_result.result:
                IStatusMessage(self.request).addStatusMessage(
                    _("Invalid data. Details: {0}".format(' '.join(user_data_validation_result.reason))), 'error'
                    )
                return

        valid_token = validate_token(token, user=user)

        #self.context.plone_log(valid_token)
        #self.context.plone_log(token)

        if valid_token:
            # We should login the user here
            self.context.acl_users.session._setupSession(str(username), self.context.REQUEST.RESPONSE)

            # TODO: Is there a nicer way of resolving the "@@google_authenticator_token_form" URL?
            IStatusMessage(self.request).addStatusMessage(_("Great! You're logged in."), 'info')
            request_data = extract_request_data(self.request)
            redirect_url = request_data.get('next_url', self.context.absolute_url())
            self.request.response.redirect(redirect_url)
        else:
            IStatusMessage(self.request).addStatusMessage(_("Invalid token or token expired."), 'error')

    def updateFields(self, *args, **kwargs):
        """
        Here the following happens. Cookie set is cleared. Thus, user is no longer logged in, but only
        after his Google Authenticator token has been validated.
        """
        logger.debug("Landed in the token hook.")

        request = self.request
        response = request['RESPONSE']
        response.setCookie('__ac', '', path='/')

        # Updating the description
        token_field = self.fields.get('token')
        if token_field:
            token_field.field.description = _(
                """Enter the verification code generated by your mobile application. """
                """If you have somehow lost your bar code, request a bar code reset """
                """<a href=\"{0}/@@request-bar-code-reset\">here</a>.""".format(self.context.absolute_url())
                )

        return super(TokenForm, self).updateFields(*args, **kwargs)


# View for the ``TokenForm``.
TokenFormView = wrap_form(TokenForm)
