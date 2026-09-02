/*
 * Parent-topic picker.
 *
 * Django's autocomplete widget is a select2 that searches on the server,
 * which is what we want for a catalogue of a few hundred topics — but it
 * ships a 250 ms keystroke delay and sizes itself to the field. This
 * re-initialises it with a 200 ms delay and full width, and sends the
 * form's current subject along so the results only ever contain topics
 * from the same subject (TopicAdmin.get_search_results reads it).
 *
 * Loaded by TopicAdmin.Media.
 */
(function ($) {
    'use strict';

    function currentSubjectId() {
        var field = document.getElementById('id_subject');
        return field ? field.value : '';
    }

    function editingTopicId() {
        // /admin/app/topic/<id>/change/
        var match = window.location.pathname.match(/\/topic\/(\d+)\/change\//);
        return match ? match[1] : '';
    }

    function reinitialise($element) {
        if ($element.data('select2')) {
            $element.select2('destroy');
        }

        $element.select2({
            ajax: {
                url: $element.data('ajax--url'),
                dataType: 'json',
                delay: 200,
                cache: true,
                data: function (params) {
                    return {
                        term: params.term,
                        page: params.page,
                        app_label: $element.data('app-label'),
                        model_name: $element.data('model-name'),
                        field_name: $element.data('field-name'),
                        // Extra, read by TopicAdmin.get_search_results:
                        subject: currentSubjectId(),
                        exclude_topic: editingTopicId()
                    };
                },
                processResults: function (data, params) {
                    params.page = params.page || 1;
                    return {
                        results: data.results,
                        pagination: { more: data.pagination ? data.pagination.more : false }
                    };
                }
            },
            allowClear: true,
            placeholder: $element.data('placeholder') || 'Search topics in this subject…',
            minimumInputLength: 0,
            width: '100%',
            theme: 'admin-autocomplete'
        });
    }

    $(function () {
        $('select.admin-autocomplete[name="parent"]').each(function () {
            reinitialise($(this));
        });

        // Changing the subject invalidates whatever parent was chosen.
        $('#id_subject').on('change', function () {
            var $parent = $('select.admin-autocomplete[name="parent"]');
            if ($parent.length) {
                $parent.val(null).trigger('change');
            }
        });
    });
})(django.jQuery);
