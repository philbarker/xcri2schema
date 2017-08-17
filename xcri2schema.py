#!/usr/bin/env python3
from sys import exit, stdout
import xml.etree.ElementTree as etree
from rdflib import Graph, Namespace, BNode, RDF, Literal, URIRef
from urllib.parse import quote_plus

# add SCHEMA to the namespaces for rdflib
SCHEMA = Namespace(u'http://schema.org/')
CONTEXT = {"@vocab": "http://schema.org/", "@language": "en"}
# and create a dictionary of XML namespaces for etree
namespaces = {'dc'    : 'http://purl.org/dc/elements/1.1/',
              'xcri'  : 'http://xcri.org/profiles/1.2/catalog',
              'mlo'   : 'http://purl.org/net/mlo',
              'xsi'   : 'http://www.w3.org/2001/XMLSchema-instance',
              'xhtml' : 'http://www.w3.org/1999/xhtml'
             }
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"
HTML_ELEMS = ('div', 'p',
              '{http://www.w3.org/1999/xhtml}div',
              '{http://www.w3.org/1999/xhtml}p')

class CourseCatalogue():
    """ A course catalogue, based on XCRI-CAP XML (CourseCatalogue.xcri, an
    instance of xml.etree.ElementTree) and RDF graph using schema.org Course
    (CourseCatalogue.g, an instance of rdflib.Graph). Expected use is
    to read in an XCRI-CAP xml file and convert it to a schema.org graph"""

    def __create_course_list_from_XCRI(self) -> URIRef:
        course_list = BNode()
        self.g.add( (course_list, RDF.type, SCHEMA.ItemList) )
        for child in self.xcri_root.findall('dc:description', namespaces):
            self.g.add( (course_list, SCHEMA.description, Literal(child.text, lang="en") ) )
        self.g.add( (course_list, SCHEMA.itemListOrder, Literal('ordered', lang='en')) )
        return course_list

    def remove_formatting(self, elem: etree.Element) -> str:
        """ a brutal method of getting rid of any formatting or other
        structuring if the content of a node in the xtree has HTML formatting.
        Useful for cleaning up descriptions and similar literals."""
        content = ''
        formatted = False
        for child in elem.iter():
            if child.tag in HTML_ELEMS:
                formatted = True
        if formatted:
            for child in elem.iter():
                content = content +' '+ child.text
            return content
        else:
            return elem.text

    def add_entity(self, elem: etree.Element, schema_type:URIRef) -> URIRef:
        uri_identifier = ''
        identifiers = elem.findall('dc:identifier', namespaces)
        if len(identifiers) > 0 :
            # create entity with @id based on URL if it is present
            # else use any other identifier
            for identifier in identifiers:
                if identifier.text.startswith('http'):
                    uri_identifier = identifier.text
                else:
                    non_uri_identifier = identifier.text
            if uri_identifier:
            # naughty people use same URL for Course & its Instance on same page
            # so add a fragment id based on schema_type type to disambiguate
                entity = URIRef(uri_identifier+'#'+str(schema_type).split('/')[-1])
            else:
                entity = URIRef(quote_plus(non_uri_identifier))
        else:
            entity = BNode()
        self.g.add( (entity, RDF.type, schema_type) )        
        for url in elem.findall('mlo:url', namespaces):
            self.g.add( (entity, SCHEMA.url, Literal(url.text, lang='en')) )
#to do: check what mlo:url is URL of: is diff to dc:identifier?
        if uri_identifier:
            u= Literal(uri_identifier, lang='en')
            self.g.add( (entity, SCHEMA.url, u) )
        for name in elem.findall('dc:title', namespaces):
            n = Literal(name.text, lang="en")
            self.g.add( (entity, SCHEMA.name, n) )
        for description in elem.findall('dc:description', namespaces):
            d = Literal(description.text, lang="en")
            self.g.add( (entity, SCHEMA.description, d) )
        return entity

    def add_provider(self, provider_elem: etree.Element) -> URIRef:
        provider = self.add_entity(provider_elem, SCHEMA.Organization)
        for location in provider_elem.findall('mlo:location', namespaces):
            address = self.add_address(location)
            self.g.add( (provider, SCHEMA.address, address) )
#to do: add sub-organizations
        return provider

    def add_educational_alignment(self, course:URIRef,
                                        targetUrl = '',
                                        targetDescription = '',
                                        targetName = '',
                                        alignmentType='',
                                        educationalFramework=''):
        if targetUrl or targetName or targetDescription :
            alignment_object = BNode()
        else:
#            raise Warning('Tried to make alignment with no target')
            print('Warning Tried to make alignment with no target')
        self.g.add( (alignment_object, RDF.type, SCHEMA.AlignmentObject) )
        self.g.add( (alignment_object, SCHEMA.alignmentType,
                                       Literal(alignmentType, 'en')) )
        self.g.add( (alignment_object, SCHEMA.educationalFramework,
                                       Literal(educationalFramework, 'en')) )
        self.g.add( (course, SCHEMA.educationalAlignment, alignment_object) )
        if targetUrl:
            u = Literal(targetUrl, 'en')
            self.g.add((alignment_object, SCHEMA.targetUrl, u))
        if targetName:
            n = Literal(targetName, 'en')
            self.g.add((alignment_object, SCHEMA.targetName, n))
        if targetDescription:
            d = Literal(targetDescription, 'en')
            self.g.add((alignment_object, SCHEMA.targetDescription, d))
        
        return

    def add_course(self, course_elem: etree.Element,
                         item_list:URIRef,
                         count:int,
                         provider:URIRef) -> URIRef:
        # add the course to the graph
        course = self.add_entity(course_elem, SCHEMA.Course)
        # use abstract for description if it is present
        for abstract in course_elem.findall('xcri:abstract', namespaces):
            self.g.remove( (course, SCHEMA.description, None) )
            d = Literal(abstract.text, lang='en')
            self.g.add( (course, SCHEMA.description, d) )
        # link the course to the ItemList (must first be multityped as ListItem)
        self.g.add( (course, RDF.type, SCHEMA.ListItem) )
        self.g.add( (course, SCHEMA.position, Literal(count, lang='en')) )
        self.g.add( (item_list, SCHEMA.itemListElement, course) )
        # link course to provider
        self.g.add( (course, SCHEMA.provider, provider) )
        # add course code, e.g. CS101, do not want to repeat url here.
        # making guesses that acceptable codes are 
        # an internalID or some id of specified type or *not* a http url
        for identifier in course_elem.findall('dc:identifier', namespaces):
            if 'courseDataProgramme:internalID' == identifier.get(XSI_TYPE):
                id_ = Literal(identifier.text, lang='en')
            elif identifier.get(XSI_TYPE):
                id_ = Literal(identifier.text, lang='en')
            elif not identifier.text.startswith('http'):
                id_ = Literal(identifier.text, lang='en')
            else:
                id_= None
            if id_: self.g.add( (course, SCHEMA.courseCode, id_) )

        # add course subject
        for subject in course_elem.findall('dc:subject', namespaces):
            self.g.add((course, SCHEMA.about, Literal(subject.text, lang='en')))
            if 'courseDataProgramme:JACS3' == subject.get(XSI_TYPE):
                self.add_educational_alignment(course, subject,
                                               alignmentType = 'EducationalSubject',
                                               educationalFramework = 'JACS',
                                               targetName=subject.text)
        # add course prerequisites
        for prereq in course_elem.findall('mlo:prerequisite', namespaces):
            text = self.remove_formatting(prereq)
            self.g.add((course, SCHEMA.coursePrerequisites, Literal(text, lang='en')))            
        return course

    def add_address(self, location:etree.Element) -> URIRef:
#to do 1. avoid unnecessary repition if many instances in same place
#      2. check differing options for how to provide venue info in XCRI
        address = BNode()
        self.g.add( (address, RDF.type, SCHEMA.PostalAddress) )
        for address_line in location.findall('mlo:address', namespaces):
            street = Literal(address_line.text, lang='en')
            self.g.add( (address, SCHEMA.streetAddress, street) )
        for town in location.findall('mlo:town', namespaces):
            locality = Literal(town.text, lang='en')
            self.g.add( (address, SCHEMA.addressLocality, locality) )
        for postcode in location.findall('mlo:postcode', namespaces):
            code = Literal(postcode.text, lang='en')
            self.g.add( (address, SCHEMA.postalCode, code) )
        for phone in location.findall('mlo:phone', namespaces):
            telephone = Literal(phone.text, lang='en')
            self.g.add( (address, SCHEMA.telephone, telephone) )
        for email in location.findall('mlo:email', namespaces):
            s_email = Literal(email.text, lang='en')
            self.g.add( (address, SCHEMA.email,s_email) )
        return address
    
    
    def add_place(self, location: etree.Element,
                        location_of: etree.Element=None) -> URIRef:
        if location_of:
            place = self.add_entity(location_of, SCHEMA.Place)
            #but let's not give places urls
            self.g.remove( (place, SCHEMA.url, None) )
        else:
            place = BNode()
            self.g.add(place, RDF.type, SCHEMA.Place)
        address = self.add_address(location)
        self.g.add( (place, SCHEMA.address, address) )
        return place

    def add_date(self, event:URIRef, prop:URIRef, date_elem:etree.Element):
        if ('dtf' in date_elem.attrib.keys()):
           date = Literal(date_elem.attrib['dtf'], lang='en')
        else:
           date = Literal(date.value, lang='en')
        self.g.add( (event, prop, date) )
        
    def create_course_mode(self, course_instance: URIRef,
                              presentation: etree.Element) -> str:
        mode = ''
        for m in presentation.findall('xcri:studyMode', namespaces):
            mode = mode + 'Available study mode: ' + m.text + '.\n'
        for m in  presentation.findall('xcri:attendanceMode', namespaces):
            mode = mode + 'Available attendance mode: ' + m.text + '.\n'
        for m in  presentation.findall('xcri:attendancePattern', namespaces):
            mode = mode + 'Available attendance pattern: ' + m.text + '.\n'
        return mode

    def add_course_offer(self, course_instance: URIRef,
                               presentation_elem: etree.Element) -> URIRef:
        offer = None
        fdate = presentation_elem.find('xcri:applyFrom', namespaces)
        udate = presentation_elem.find('xcri:applyUntil', namespaces)
        cost = presentation_elem.find('mlo:cost', namespaces)
        applyTo = presentation_elem.find('xcri:applyTo', namespaces)
        if ((fdate != None) or (udate != None)
                or (cost != None) or (applyTo != None)):
            offer = BNode()
            self.g.add( (offer, RDF.type, SCHEMA.Offer) )
            if (fdate != None):
                self.add_date(offer, SCHEMA.availabilityStarts, fdate)
            if (udate != None):
                self.add_date(offer, SCHEMA.availabilityEnds, udate)
            if (applyTo != None):
                place = BNode()
                self.g.add( (place, RDF.type, SCHEMA.Place) )
                if applyTo.text.startswith('http'):
                    url = Literal(applyTo.text, lang='en')
                    self.g.add((place, SCHEMA.url, url))
                else:
                    name = Literal(applyTo.text, lang='en')
                    self.g.add((place, SCHEMA.name, name))
                self.g.add( (offer, SCHEMA.availableAtOrFrom, place) )
            if (cost != None):
                for acost in presentation_elem.findall('mlo:cost', namespaces):
                    price_spec = BNode()
                    self.g.add((price_spec, RDF.type, SCHEMA.PriceSpecification))
                    desc = Literal(self.remove_formatting(acost), lang='en')
                    self.g.add( (price_spec, SCHEMA.description, desc ) )
                    self.g.add( (offer, SCHEMA.priceSpecification, price_spec))
        return offer
    
    
    def add_course_instance(self, presentation_elem: etree.Element,
                            course: URIRef) -> URIRef:
        instance = self.add_entity(presentation_elem, SCHEMA.CourseInstance)
        self.g.add( (course, SCHEMA.hasCourseInstance, instance) )
        # add location: there can be only one!
        count = 0
        for venue in presentation_elem.findall('xcri:venue', namespaces):
            for provider in venue.findall('xcri:provider', namespaces):
                for location in provider.findall('mlo:location', namespaces):
                    place = self.add_place(location, location_of=provider)          
                    self.g.add( (instance, SCHEMA.location, place) )
                    if count > 1:
                        print('Warning, CourseInstance in several places')
                    count += 1
        # add start date: there can be only one!
        count = 0
        for date in presentation_elem.findall('mlo:start', namespaces):
            self.add_date(instance, SCHEMA.startDate, date)
            if count > 1:
                print('Warning, CourseInstance start more than once')
            count += 1
        # add end date: there can be only one!
        count = 0
        for date in presentation_elem.findall('xcri:end', namespaces):
            self.add_date(instance, SCHEMA.endDate, date)
            if count > 1:
                print('Warning, CourseInstance ends more than once')
            count += 1
        # add duration
        for duration in presentation_elem.findall('mlo:duration', namespaces):
            if ('interval' in duration.attrib.keys()):
               s_duration = Literal(duration.attrib['interval'], lang='en')
            else:
               s_duration = Literal(duration, lang='en')
            self.g.add( (instance, SCHEMA.duration, s_duration) )
        # concoct a course mode out of various xcri modes, if available
        course_mode = self.create_course_mode(instance, presentation_elem)
        if course_mode:
            mode = Literal(course_mode, lang='en')
            self.g.add( (instance, SCHEMA.courseMode, mode) )
        # add Offers, assume only one (though may have multiple & complex costing)
        course_offer = self.add_course_offer(instance, presentation_elem)
        if course_offer:
            self.g.add( (instance, SCHEMA.offers, course_offer) )
        return instance

    def add_courses_by_provider(self, course_list:URIRef):
        counter = int(0)
        for provider_elem in self.xcri_root.findall('xcri:provider', namespaces):
            provider = self.add_provider(provider_elem)
            for course_elem in provider_elem.findall('xcri:course', namespaces):
                counter += 1
                course = self.add_course(course_elem, course_list, counter, provider)
                for presentation_elem in course_elem.findall('xcri:presentation', namespaces):
                    course_instance = self.add_course_instance(presentation_elem, course)

    def __init__(self, xcri_in: str):
        """ Reads an XCRI-CAP file and from it builds a schema.org graph
            input: xcri_in - the filename of of the XCRI-CAP file
            returns: CourseCatalogue.xcri - xml.etree.ElementTree of XCRI
            CourseCatalogue.xcri_root - the root of the XCRI tree
            CourseCatalogue.g - a rdflib.Graph using schema.org Course
            CourseCatalogue.course_list - schema.org ItemList of Courses
        """
        # create a new graph to store the catalogue info
        self.g = Graph()
        self.g.bind("schema", SCHEMA)        
#to do: see XML vulnerabilities of etree & check for entity expansion
        try:
            self.xcri = etree.parse(xcri_in)
            self.xcri_root = self.xcri.getroot()
        except IOError:
            print("File ", self.in_file, " could not be opened")
            sys.exit()
# To do: identify language from XML attrib
        self.course_list = self.__create_course_list_from_XCRI()
        self.add_courses_by_provider(self.course_list)
        

if __name__ == "__main__":
    print("Running with test params is better than running with knives")
    xcri_in="./exampleData/PG-Generic-XCRI-CAP-1.2.xml"
    schema_out="./exampleData/PG-Generic-XCRI-CAP-1.2.json"
#to do: specifiy xcri_in from command line
#to do: xcri_in as feed url
    print("Input file name: ", xcri_in)
    print("Output file name: ", schema_out)
    catalogue = CourseCatalogue(xcri_in)
    catalogue.g.serialize( format = 'json-ld',
                           destination=schema_out, context=CONTEXT )

