document.addEventListener("DOMContentLoaded", function() {

    // Function to add a styled colon after specific headers
    function addStyledColonAfterHeaders(headers, headerTexts) {
        headers.forEach(function(header) {
            if (header && header.nextSibling && header.nextSibling.nodeType === Node.TEXT_NODE &&
                    header.nextSibling.textContent.trim() === ":") {
                header.parentNode.removeChild(header.nextSibling);
            }
            if (headerTexts.includes(header.textContent.trim())) {
                var colonSpan = document.createElement("span");
                colonSpan.textContent = ":";
                colonSpan.classList.add("examples-colon"); // Optional: Add a class for styling
                header.parentNode.insertBefore(colonSpan, header.nextSibling);
            }
        });
    }

    // Apply the function to the examples headers
    var examplesHeaders = document.querySelectorAll("p > strong");
    addStyledColonAfterHeaders(examplesHeaders, ["Examples", "Illustration", "Define a proxy object that inherits from this class"]);

    // Add a colon to rubric paragraphs
    var rubricParagraphs = document.querySelectorAll("p.rubric");
    rubricParagraphs.forEach(function(paragraph) {
        if (!paragraph.textContent.trim().endsWith(":")) {
            paragraph.textContent = paragraph.textContent.trim() + ":";
        }
    });

});
