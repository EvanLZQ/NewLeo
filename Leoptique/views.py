from django.http import JsonResponse


def upload_image(request):
    if request.method == 'POST':
        image_file = request.FILES.get('file')
        # handle uploaded file
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})
