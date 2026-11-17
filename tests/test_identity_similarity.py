from difflib import SequenceMatcher

from scrapers.identity import validate_pdf_identity


def certificate(name, doc='1125848987'):
    return f'Se registra el(la) señor(a) {name}, identificado(a) con Tarjeta de Identidad número {doc}, en estado Activo.'


def test_accepts_spelling_difference_and_reports_scores():
    result = validate_pdf_identity(certificate('JHONY DANILO VERA SALAZAR'), '1125848987', ['YONY DANILO', 'VERA SALAZAR'])
    assert result.status == 'OK'
    assert result.document_matches
    assert result.surnames_score == 100
    assert result.names_score == 86.96
    assert result.overall_score == 93.88
    assert result.review
    assert 'umbral 85%' in result.detail


def test_document_must_match_even_for_identical_name():
    for doc in ['91125848987', '11258489879', '1125848988', '1.125.848.987.9']:
        result = validate_pdf_identity(certificate('JHONY DANILO VERA SALAZAR', doc), '1125848987', ['JHONY DANILO', 'VERA SALAZAR'])
        assert result.status == 'ERROR', doc
        assert result.overall_score is None


def test_document_in_footer_cannot_override_holder_document():
    text = certificate('JHONY DANILO VERA SALAZAR', '1125848988') + ' Verificación 1125848987'
    assert validate_pdf_identity(text, '1125848987', ['JHONY DANILO', 'VERA SALAZAR']).status == 'ERROR'


def test_formatted_document_and_accents_match():
    result = validate_pdf_identity(certificate('SAMUEL GONZÁLEZ MARÍN', '1.125.848.987'), '1125848987', ['SAMUEL', 'GONZALEZ MARIN'])
    assert result.status == 'OK'
    assert result.overall_score == 100
    assert not result.review


def test_additional_given_name_remains_accepted():
    result = validate_pdf_identity(certificate('SAMUEL LINA GONZALEZ MARIN'), '1125848987', ['SAMUEL', 'GONZALEZ MARIN'])
    assert result.status == 'OK'
    assert result.overall_score == 100
    assert result.review


def test_global_score_can_accept_small_surname_difference():
    result = validate_pdf_identity(certificate('JHONY DANILO VERA SALASAR'), '1125848987', ['JHONY DANILO', 'VERA SALAZAR'])
    assert result.status == 'OK'
    assert result.surnames_score < 100
    assert result.review


def test_low_global_match_requires_manual_review():
    result = validate_pdf_identity(certificate('PEDRO LUIS GOMEZ PEREZ'), '1125848987', ['YONY DANILO', 'VERA SALAZAR'])
    assert result.status == 'REVISAR'
    assert result.overall_score < 85
    assert result.review


def test_missing_names_and_unknown_format_require_review():
    for names in [[], ['YONY'], ['YONY', '']]:
        assert validate_pdf_identity(certificate('JHONY DANILO VERA SALAZAR'), '1125848987', names).status == 'REVISAR'
    result = validate_pdf_identity('Titular no reconocible 1125848987', '1125848987', ['YONY', 'VERA SALAZAR'])
    assert result.status == 'REVISAR'
    assert result.overall_score is None


def test_unrounded_threshold_controls_acceptance():
    expected = 'YONY DANILO VERA SALAZAR'
    actual = 'JHONY DANILO VERA SALAZAR'
    exact_score = SequenceMatcher(None, expected, actual).ratio() * 100
    assert validate_pdf_identity(certificate(actual), '1125848987', ['YONY DANILO', 'VERA SALAZAR'], threshold=exact_score).status == 'OK'
    assert validate_pdf_identity(certificate(actual), '1125848987', ['YONY DANILO', 'VERA SALAZAR'], threshold=exact_score + .001).status == 'REVISAR'


def test_surnames_before_names_match_without_review():
    result = validate_pdf_identity(certificate('QUIÑONES ARCE WALTER', '1001270359'), '1001270359', ['WALTER', 'QUINONES ARCE'])
    assert result.status == 'OK'
    assert result.surnames_score == 100
    assert result.names_score == 100
    assert result.overall_score == 100
    assert not result.review
    assert result.certificate_name == 'QUINONES ARCE WALTER'
    assert 'orden del certificado: apellidos y nombres' in result.detail


def test_surnames_first_supports_spelling_difference_and_additional_names():
    for name, expected, overall in [
        ('VERA SALAZAR JHONY DANILO', ['YONY DANILO', 'VERA SALAZAR'], 93.88),
        ('GONZALEZ MARIN SAMUEL LINA', ['SAMUEL', 'GONZALEZ MARIN'], 100),
    ]:
        result = validate_pdf_identity(certificate(name), '1125848987', expected)
        assert result.status == 'OK'
        assert result.overall_score == overall
        assert result.review


def test_reordered_names_cannot_override_wrong_document_or_missing_surname():
    result = validate_pdf_identity(certificate('QUINONES ARCE WALTER', '1001270358'), '1001270359', ['WALTER', 'QUINONES ARCE'])
    assert result.status == 'ERROR'
    result = validate_pdf_identity(certificate('QUINONES WALTER', '1001270359'), '1001270359', ['WALTER', 'QUINONES ARCE'])
    assert result.status == 'REVISAR'
    assert result.overall_score < 85
