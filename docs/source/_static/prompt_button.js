$(document).ready(function() {
    /* Add a [>>>] button on the top-right corner of code samples to hide the >>> and ... prompts
     * and the output, thus making the code copyable.
     * Resource: https://docs.python.org/3/_static/copybutton.js */
    let div = $('.highlight-python .highlight,' +
                '.highlight-python3 .highlight,' +
                '.highlight-pycon .highlight,' +
                '.highlight-default .highlight');
    let pre = div.find('pre');

    // Get the styles from the current theme
    pre.parent().parent().css('position', 'relative');
    let hide_text = 'Hide the prompts and output';
    let show_text = 'Show the prompts and output';
    let border_width = pre.css('border-top-width');
    let border_style = pre.css('border-top-style');
    let border_color = pre.css('border-top-color');
    let button_styles = {
        'cursor':'pointer',
        'position': 'absolute',
        'top': '0',
        'right': '0',
        'border-color': border_color,
        'border-style': border_style,
        'border-width': border_width,
        'color': border_color,
        'text-size': '75%',
        'font-family': 'monospace',
        'padding-left': '0.2em',
        'padding-right': '0.2em',
        'border-radius': '0 3px 0 0'
    }

    // Create and add the button to all the code blocks that contain >>>
    div.each(function() {
        let jthis = $(this);
        if (jthis.find('.gp').length > 0) {
            let button = $('<span class="promptbutton">&gt;&gt;&gt;</span>');
            button.css(button_styles)
            button.attr('title', hide_text);
            button.data('hidden', 'false');
            jthis.prepend(button);
        }
        /* tracebacks (.gt) contain bare text elements that need to be wrapped
         * in a span to work with .nextUntil() (see later) */
        jthis.find('pre:has(.gt)').contents().filter(function() {
            return ((this.nodeType === 3) && (this.data.trim().length > 0));
        }).wrap('<span>');
    });

    // Define the behavior of the button when it's clicked
    $('.promptbutton').click(function(e){
        e.preventDefault();
        let button = $(this);
        if (button.data('hidden') === 'false') {
            // hide the code output
            button.parent().find('.go, .gp, .gt').hide();
            button.next('pre').find('.gt').nextUntil('.gp, .go').css('visibility', 'hidden');
            button.css('text-decoration', 'line-through');
            button.attr('title', show_text);
            button.data('hidden', 'true');
        } else {
            // show the code output
            button.parent().find('.go, .gp, .gt').show();
            button.next('pre').find('.gt').nextUntil('.gp, .go').css('visibility', 'visible');
            button.css('text-decoration', 'none');
            button.attr('title', hide_text);
            button.data('hidden', 'false');
        }
    });
});
