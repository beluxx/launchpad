from zope.app.pagetemplate.viewpagetemplatefile import ViewPageTemplateFile

from canonical.lp.dbschema import BugSeverity

from canonical.rosetta.browser import ViewProduct

class SourcePackageView(object):
    def __init__(self, context, request):
        self.context = context
        self.request = request

    def affectedBinaryPackages(self):
        '''Return a list of [BinaryPackage, {severity -> count}]'''
        m = {}
        sevdef = {}
        for i in BugSeverity.items:
            sevdef[i.name] = 0
        for bugass in self.context.bugs:
            binarypackage = bugass.binarypackage
            if binarypackage:
                severity = BugSeverity.items[i].name
                stats = m.setdefault(binarypackage, sevdef.copy())
                m[binarypackage][severity] += 1
        rv = m.items()
        rv.sort(lambda a,b: cmp(a.id, b.id))
        return rv

class SourcePackageTranslationsView(object):
    translationPortlet = ViewPageTemplateFile(
        '../templates/portlet-translations-sourcepackage.pt')

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def productTranslations(self):
        if self.context.sourcepackage.product:
            return ViewProduct(self.context.sourcepackage.product, self.request)
        return None
