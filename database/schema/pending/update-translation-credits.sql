-- Delete existing, non-published submissions for translation credits
DELETE FROM posubmission WHERE id IN (
    SELECT posubmission.id
        FROM posubmission,
	     pomsgset,
	     potmsgset,
	     pomsgid
	WHERE
	    posubmission.pomsgset=pomsgset.id AND 
	    potmsgset=potmsgset.id AND
	    primemsgid=pomsgid.id AND
	    published IS NOT TRUE AND
	    (msgid='translation-credits' OR
	     msgid='translator-credits' OR
	     msgid='translator_credits' OR
	     msgid=E'_:EMAIL OF TRANSLATORS\nYour emails' OR
	     msgid=E'_:NAME OF TRANSLATORS\nYour names'));

-- Set any existing inactive published translations as active
UPDATE posubmission SET active=TRUE WHERE id IN (
    SELECT posubmission.id
        FROM posubmission,
	     pomsgset,
	     potmsgset,
	     pomsgid
	WHERE
	    posubmission.pomsgset=pomsgset.id AND 
	    potmsgset=potmsgset.id AND
	    primemsgid=pomsgid.id AND
	    published IS TRUE AND
	    (msgid='translation-credits' OR
	     msgid='translator-credits' OR
	     msgid='translator_credits' OR
	     msgid=E'_:EMAIL OF TRANSLATORS\nYour emails' OR
	     msgid=E'_:NAME OF TRANSLATORS\nYour names'));

-- set sequence number to -1?
